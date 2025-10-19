import os
import secrets
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from src.client.models import Incident, IncidentType
from src.client.qudata import QudataClient
from src.server.models import (
    CreateInstance,
    InstanceAction,
    InstanceCreated,
    ManageInstance,
)
from src.service.fingerprint import get_fingerprint
from src.storage.state import InstanceState, clear_state, get_current_state, save_state
from src.utils.ports import get_free_port
from src.utils.system import run_command
from src.utils.xlogging import get_logger

logger = get_logger(__name__)

STORAGE_PATH = Path("./instance_storage")
# RUNTIME = "io.containerd.run.kata.v2"
BAN_FLAG_PATH = Path("var/lib/qudata/.ban-flag")


def _shred_file(file_path: str):
    if file_path and os.path.exists(file_path):
        logger.critical(f"Shredding file at {file_path}")
        run_command(["shred", "-u", "-n", "1", file_path])


def decrypt_dek(wrapped_dek: str) -> str | None:
    # TODO: This requires a full implementation in `secure.py`
    logger.warning(
        "Using a placeholder DEK decryption. This is INSECURE for production."
    )
    if wrapped_dek:
        return secrets.token_hex(16)
    return None


def create_new_instance(params: CreateInstance) -> tuple[bool, dict | None, str | None]:
    state = get_current_state()
    if state.status != "destroyed":
        err = f"An instance '{state.instance_id}' already exists with status '{state.status}'. Please delete it first."
        logger.error(err)
        return False, None, err

    logger.info(
        f"Received request to create a new instance with image {params.image}:{params.image_tag}"
    )
    instance_id = str(uuid.uuid4())

    logger.warning(
        "SECURITY DISABLED: Running in 'vanilla Docker' mode. LUKS and Kata are bypassed."
    )

    logger.info("Preparing to launch instance via standard Docker...")

    cpu_cores = (params.env_variables or {}).pop("QUDATA_CPU_CORES", "1")
    memory_gb = (params.env_variables or {}).pop("QUDATA_MEMORY_GB", "2")
    gpu_count = (params.env_variables or {}).pop("QUDATA_GPU_COUNT", "0")

    docker_command = [
        "docker",
        "run",
        "-d",
        "--rm",
        f"--cpus={cpu_cores}",
        f"--memory={memory_gb}g",
    ]

    if int(gpu_count) > 0:
        docker_command.append(f"--gpus=count={gpu_count}")

    allocated_ports = {}
    for container_port, host_port_def in (params.ports or {}).items():
        host_port = str(
            host_port_def if str(host_port_def).lower() != "auto" else get_free_port()
        )
        docker_command.extend(["-p", f"{host_port}:{container_port}"])
        allocated_ports[container_port] = host_port

    for key, value in (params.env_variables or {}).items():
        if key == "QUDATA_WRAPPED_DEK":
            continue
        docker_command.extend(["-e", f"{key}={value}"])

    if params.ssh_enabled and "22" not in (params.ports or {}):
        host_ssh_port = str(get_free_port())
        docker_command.extend(["-p", f"{host_ssh_port}:22"])
        allocated_ports["22"] = host_ssh_port

    image_full_name = f"{params.image}:{params.image_tag}"
    docker_command.append(image_full_name)
    if params.command:
        docker_command.extend(params.command.split())

    success, container_id, stderr = run_command(docker_command)
    if not success or not container_id:
        return False, None, f"Failed to run Docker container: {stderr}"

    container_id = container_id.strip()
    logger.info(f"Container '{container_id[:12]}' started successfully.")

    new_state = InstanceState(
        instance_id=instance_id,
        container_id=container_id,
        status="running",
        allocated_ports=allocated_ports,
    )
    if not save_state(new_state):
        run_command(["docker", "rm", "-f", container_id])
        return (
            False,
            None,
            "CRITICAL: Failed to save state after container creation. Rolled back.",
        )

    created_data = InstanceCreated(success=True, ports=allocated_ports)
    return True, asdict(created_data), None


def manage_instance(params: ManageInstance) -> tuple[bool, str | None]:
    state = get_current_state()
    if state.status == "destroyed" or not state.container_id:
        return False, "No active instance to manage."

    action_map = {
        InstanceAction.stop: (["docker", "stop", state.container_id], "paused"),
        InstanceAction.start: (["docker", "start", state.container_id], "running"),
        InstanceAction.restart: (["docker", "restart", state.container_id], "running"),
    }

    if params.action not in action_map:
        return False, f"Unknown action: {params.action}"

    command, new_status = action_map[params.action]

    logger.info(
        f"Executing action '{params.action}' on container {state.container_id[:12]}..."
    )
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


def get_instance_logs(
    container_id: str, tail: int = 100
) -> tuple[bool, str | None, str | None]:
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
    logger.critical("--- STARTING (Simplified) SELF-DESTRUCT SEQUENCE ---")
    if state.container_id:
        logger.critical(f"Forcefully removing container {state.container_id[:12]}...")
        run_command(["docker", "rm", "-f", state.container_id])

    logger.critical("Shredding agent's sensitive state...")
    clear_state()

    try:
        BAN_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fingerprint = get_fingerprint()
        BAN_FLAG_PATH.write_text(fingerprint)
        logger.info(
            f"Banned with fingerprint: {fingerprint[:12]}, "
            f"stored at {BAN_FLAG_PATH}"
        )
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
