import os
import time
import uuid
import secrets
from pathlib import Path
from dataclasses import asdict

from src.client.models import Incident, IncidentType
from src.client.qudata import QudataClient
from src.server.models import CreateInstance, ManageInstance, InstanceAction, InstanceCreated
from src.service.fingerprint import get_fingerprint
from src.storage.state import get_current_state, save_state, clear_state, InstanceState
from src.utils.ports import get_free_port
from src.utils.system import run_command
from src.utils.xlogging import get_logger

logger = get_logger(__name__)

STORAGE_PATH = Path("./instance_storage")
RUNTIME = "io.containerd.run.kata.v2"
BAN_FLAG_PATH = Path("var/lib/qudata/.ban-flag")


def _shred_file(file_path: str):
    if file_path and os.path.exists(file_path):
        logger.critical(f"Shredding file at {file_path}")
        run_command(["shred", "-u", "-n", "1", file_path])

def decrypt_dek(wrapped_dek: str) -> str | None:
    # TODO: This requires a full implementation in `secure.py`
    logger.warning(
        "Using a placeholder DEK decryption. This is INSECURE for production.")
    if wrapped_dek:
        return secrets.token_hex(16)
    return None


def create_new_instance(params: CreateInstance) -> tuple[
    bool, dict | None, str | None]:
    state = get_current_state()
    if state.status != "destroyed":
        err = (f"An instance '{state.instance_id}' already exists with status '{state.status}'. "
               f"Please delete it first.")
        logger.error(err)
        return False, None, err

    logger.info(
        f"Received request to create a new instance with image {params.image}"
        f":{params.image_tag}")
    STORAGE_PATH.mkdir(exist_ok=True, mode=0o700)
    instance_id = str(uuid.uuid4())

    wrapped_dek = (params.env_variables or {}).pop("QUDATA_WRAPPED_DEK", None)
    if not wrapped_dek:
        err = ("QUDATA_WRAPPED_DEK is missing from env_variables. "
               "Cannot proceed with encrypted storage.")
        logger.error(err)
        return False, None, err

    dek = decrypt_dek(wrapped_dek)
    if not dek:
        err = "Failed to decrypt DEK."
        logger.error(err)
        return False, None, err

    luks_device_path = STORAGE_PATH / f"{instance_id}.luks"
    luks_mapper_name = f"qudata-inst-{instance_id[:8]}"

    logger.info(
        f"Creating LUKS volume at '{luks_device_path}' with size {params.storage_gb}GB...",
    )

    try:
        with open(luks_device_path, "wb") as f:
            f.seek(params.storage_gb * (1024 ** 3) - 1)
            f.write(b'\0')
        os.chmod(luks_device_path, 0o600)
    except IOError as e:
        return False, None, f"Failed to create LUKS file container: {e}"

    success, _, stderr = run_command(
        ["cryptsetup", "-q", "luksFormat", "--type", "luks2",
         str(luks_device_path)],
        input_data=dek
    )
    if not success:
        luks_device_path.unlink(missing_ok=True)
        return False, None, f"Failed to format LUKS volume: {stderr}"

    success, _, stderr = run_command(
        ["cryptsetup", "luksOpen", str(luks_device_path), luks_mapper_name],
        input_data=dek
    )
    if not success:
        luks_device_path.unlink(missing_ok=True)
        return False, None, f"Failed to open LUKS volume: {stderr}"

    dek = "0" * len(dek)
    logger.info("DEK has been used and wiped from memory.")

    mapped_device_path = f"/dev/mapper/{luks_mapper_name}"
    success, _, stderr = run_command(["mkfs.ext4", "-q", mapped_device_path])
    if not success:
        run_command(["cryptsetup", "luksClose", luks_mapper_name])
        luks_device_path.unlink(missing_ok=True)
        return False, None, f"Failed to create filesystem on LUKS volume: {stderr}"

    logger.info("Preparing to launch instance via Kata Containers...")

    cpu_cores = (params.env_variables or {}).pop("QUDATA_CPU_CORES", "1")
    memory_gb = (params.env_variables or {}).pop("QUDATA_MEMORY_GB", "2")
    gpu_count = (params.env_variables or {}).pop("QUDATA_GPU_COUNT", "0")

    docker_command = [
        "docker", "run",
        "-d", "--rm",
        "--runtime", RUNTIME,
        f"--cpus={cpu_cores}",
        f"--memory={memory_gb}g",
    ]

    if int(gpu_count) > 0:
        docker_command.append(f"--gpus=count={gpu_count}")

    allocated_ports = {}
    for container_port, host_port_def in (params.ports or {}).items():
        host_port = str(host_port_def if str(
            host_port_def).lower() != "auto" else get_free_port())
        docker_command.extend(["-p", f"{host_port}:{container_port}"])
        allocated_ports[container_port] = host_port

    volume_mount_string = f"type=bind,source={mapped_device_path},destination=/data"
    docker_command.extend(["--mount", volume_mount_string])

    for key, value in (params.env_variables or {}).items():
        docker_command.extend(["-e", f"{key}={value}"])

    if params.ssh_enabled and '22' not in (params.ports or {}):
        host_ssh_port = str(get_free_port())
        docker_command.extend(["-p", f"{host_ssh_port}:22"])
        allocated_ports['22'] = host_ssh_port

    image_full_name = f"{params.image}:{params.image_tag}"
    docker_command.append(image_full_name)
    if params.command:
        docker_command.extend(params.command.split())

    success, container_id, stderr = run_command(docker_command)
    if not success or not container_id:
        run_command(["cryptsetup", "luksClose", luks_mapper_name])
        luks_device_path.unlink(missing_ok=True)
        return False, None, f"Failed to run Docker container with Kata: {stderr}"

    container_id = container_id.strip()
    logger.info(
        f"Container '{container_id[:12]}' started successfully inside a Micro-VM.")

    new_state = InstanceState(
        instance_id=instance_id,
        container_id=container_id,
        status="running",
        luks_device_path=str(luks_device_path),
        luks_mapper_name=luks_mapper_name,
        allocated_ports=allocated_ports,
    )
    if not save_state(new_state):
        run_command(["docker", "rm", "-f", container_id])
        run_command(["cryptsetup", "luksClose", luks_mapper_name])
        return False, None, "CRITICAL: Failed to save state after container creation. Rolled back."

    created_data = InstanceCreated(success=True, ports=allocated_ports)
    return True, asdict(created_data), None

def manage_instance(params: ManageInstance) -> tuple[bool, str | None]:
    state = get_current_state()
    if state.status == "destroyed" or not state.container_id:
        return False, "No active instance to manage."

    action_map = {
        InstanceAction.stop: (["docker", "stop", state.container_id],
                              "paused"),
        InstanceAction.start: (["docker", "start", state.container_id],
                               "running"),
        InstanceAction.restart: (["docker", "restart", state.container_id],
                                 "running"),
    }

    if params.action not in action_map:
        return False, f"Unknown action: {params.action}"

    command, new_status = action_map[params.action]

    logger.info(
        f"Executing action '{params.action}' on container {state.container_id[:12]}...")
    success, _, stderr = run_command(command)

    if success:
        state.status = new_status
        save_state(state)
        logger.info(f"Action '{params.action}' completed successfully.")
        return True, None
    else:
        err = f"Failed to execute action '{params.action}': {stderr}"
        logger.error(err)
        state.status = "error"
        save_state(state)
        return False, err


def delete_instance() -> tuple[bool, str | None]:
    state = get_current_state()
    if state.status == "destroyed":
        logger.info("No instance to delete. State is already clean.")
        return True, None

    emergency_self_destruct()
    logger.info("Instance deletion completed via self-destruct sequence.")
    return True, None


def get_instance_logs(container_id: str, tail: int = 100) -> tuple[
    bool, str | None, str | None]:
    if not container_id:
        return False, None, "Container ID is missing."

    logger.info(f"Fetching logs for container {container_id[:12]}...")
    command = ["docker", "logs", f"--tail={tail}", container_id]

    success, stdout, stderr = run_command(command)

    if success:
        return True, stdout or stderr, None
    else:
        full_log_output = f"STDERR: {stderr}\nSTDOUT: {stdout}"
        return False, None, full_log_output


def emergency_self_destruct() -> None:
    state = get_current_state()

    logger.critical("----- STARTING SELF-DESTRUCT PROCEDURE -----")

    if state.container_id:
        logger.critical(f"Removing container {state.container_id[:12]}...")
        run_command(["docker", "rm", "-f", state.container_id])

    if state.luks_mapper_name:
        logger.critical(f"Closing LUKS volume '{state.luks_mapper_name}'...")
        run_command(["cryptsetup", "luksClose", state.luks_mapper_name])

    _shred_file(state.luks_device_path)

    logger.critical("Shredding agent`s state")

    keyring_path = "~/.local/share/keyrings/qudata-agent.keyring"
    _shred_file(os.path.expanduser(keyring_path))

    clear_state()

    try:
        BAN_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fingerprint = get_fingerprint()
        BAN_FLAG_PATH.write_text(fingerprint)
        logger.info(f"Banned with fingerprint: {fingerprint[:12]}, stored at {BAN_FLAG_PATH}")
    except Exception as e:
        logger.error("Failed")

    try:
        client = QudataClient()
        event = Incident(
            incident_type=IncidentType.privacy_corrupted,
            timestamp=int(time.time()),
            instances_killed=True,
        )
        client.send_incident(event)
        logger.info("Incident reported to Qudata server.")
    except Exception as e:
        logger.error(f"Failed to report about the incident: {e}")

    logger.critical("----- SELF-DESTRUCT PROCEDURE COMPLETE -----")