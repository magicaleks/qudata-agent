import os
import subprocess
import sys
import time
from multiprocessing import Process, Pipe
from threading import Thread
import subprocess
import psutil

from src import runtime
from src.security.auth_daemon import auth_daemon
from src.service.fingerprint import get_fingerprint
from src.service.instances import emergency_self_destruct
from src.client.qudata import QudataClient
from src.client.models import Stats, InitAgent
from src.storage.state import get_current_state
from src.utils.enums import InstanceStatus


def run_agent_process(pipe_conn):
    try:
        client = QudataClient()
        agent_secret = client._client.headers.get("X-Agent-Secret")

        if not agent_secret:
            print(
                "INFO: No agent secret found. Performing initial registration (init)...")
            try:
                init_data = InitAgent(
                    agent_id="placeholder-id", #заглушка
                    agent_port=8000,
                    address=runtime.agent_address(),
                    fingerprint=get_fingerprint(),
                    pid=runtime.agent_pid()
                )

                agent_response = client.init(init_data)
                print(
                    f"INFO: Agent initialization successful. Secret received: {agent_response.secret_key is not None}")
            except Exception as e:
                print(f"FATAL: Agent initialization failed: {e}",
                      file=sys.stderr)
                return
        else:
            print("INFO: Agent secret found. Skipping initialization.")

        auth_daemon_thread = Thread(target=auth_daemon, daemon=True)
        auth_daemon_thread.start()

        def heartbeat_to_guardian_thread():
            while True:
                try:
                    pipe_conn.send("AGENT_PULSE")
                    time.sleep(1)
                except (IOError, EOFError):
                    print(
                        "CRITICAL: Guardian process disconnected! Initiating self-destruct.",
                        file=sys.stderr)
                    emergency_self_destruct()
                    exit(1)

        hb_thread = Thread(target=heartbeat_to_guardian_thread, daemon=True)
        hb_thread.start()

        def stats_heartbeat_thread():
            time.sleep(5)
            client = QudataClient()
            while True:
                try:
                    state = get_current_state()
                    if state.status == "destroyed":
                        print("INFO: No active instance. Stats heartbeat is idle.")
                        time.sleep(15)
                        continue

                    try:
                        container_status_enum = InstanceStatus(state.status)
                    except ValueError:
                        container_status_enum = InstanceStatus.error

                    stats_data = Stats(
                        cpu_util=psutil.cpu_percent(),
                        ram_util=psutil.virtual_memory().percent,
                        instance_status=container_status_enum,
                    )
                    # небольшое пояснение, сбор других данных чуть позже добавлю
                    print(
                        f"INFO: Sending stats heartbeat. Current instance status: {stats_data.instance_status.value}")
                    client.send_stats(stats_data)

                except Exception as e:
                    print(f"ERROR: Failed to send stats heartbeat: {e}",
                          file=sys.stderr)

                # Ждем 15 секунд
                time.sleep(15)

        stats_thread = Thread(target=stats_heartbeat_thread, daemon=True)
        stats_thread.start()

        print(
            "INFO: All agent threads (Auth, Guardian Heartbeat, Stats Heartbeat) are running.")
        print("INFO: Starting Gunicorn server...")

        gunicorn_command = [
            sys.executable,
            "-m",
            "gunicorn",
            "-w",
            "3",
            "-b",
            "0.0.0.0:8000",
            "--chdir",
            ".",
            "src.server.server:app",
        ]

        process = subprocess.run(gunicorn_command)
        print(
            f"INFO: Gunicorn process terminated with code {process.returncode}.",
            file=sys.stderr,
        )

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"FATAL ERROR IN AGENT PROCESS: {e}", file=sys.stderr)
        try:
            pipe_conn.send(f"AGENT_DIED:{e}")
        except:
            pass


def run_guardian_process(pipe_conn, parent_pid):
    print("INFO: Guardian process started.")
    last_pulse_time = time.time()

    def check_parent():
        try:
            os.kill(parent_pid, 0)
            return True
        except OSError:
            return False

    while True:
        try:
            if pipe_conn.poll(5):
                signal = pipe_conn.recv()
                if signal == "AGENT_PULSE":
                    last_pulse_time = time.time()
                elif isinstance(signal, str) and signal.startswith(
                        "AGENT_DIED"):
                    print(
                        f"CRITICAL: Guardian received fatal error from main agent: {signal}",
                        file=sys.stderr)
                    break
            else:
                if time.time() - last_pulse_time > 5:
                    print(
                        "CRITICAL: Main agent process is unresponsive! Initiating self-destruct.",
                        file=sys.stderr)
                    emergency_self_destruct()
                    break

            if not check_parent():
                print(
                    "INFO: Main launcher process is gone. Guardian is shutting down.",
                    file=sys.stderr)
                break

            time.sleep(1)

        except (IOError, EOFError):
            print(
                "CRITICAL: Communication pipe broke. Main agent is dead. Initiating self-destruct.",
                file=sys.stderr)
            emergency_self_destruct()
            break


def main_launcher():
    agent_pipe, guardian_pipe = Pipe()

    guardian = Process(target=run_guardian_process,
                       args=(guardian_pipe, os.getpid()))
    guardian.daemon = True
    guardian.start()

    while True:
        agent = Process(target=run_agent_process, args=(agent_pipe,))
        agent.start()
        print(f"INFO: Launcher started main agent with PID: {agent.pid}")

        agent.join()

        if guardian.is_alive():
            print(
                "WARNING: Main agent process terminated unexpectedly. Restarting in 3 seconds...",
                file=sys.stderr)
            time.sleep(3)
        else:
            print(
                "CRITICAL: Guardian process is also dead. Shutting down launcher.",
                file=sys.stderr)
            break


if __name__ == "__main__":
    if "type=agent" in sys.argv:
        try:
            main_launcher()
        except KeyboardInterrupt:
            print("\nLauncher terminated by user.")
    else:
        print(
            "This is the QuData Agent launcher. To run in agent mode, use 'type=agent'.")
        print("To use the CLI, please use the 'qudata-cli' package.")
        sys.exit(1)