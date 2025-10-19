# import signal
import os
import sys
import time
import subprocess
from threading import Thread
from multiprocessing import Process, Pipe

from src.agent import cli
from src.security.auth_daemon import auth_daemon
from src.service.instances import emergency_self_destruct


def run_agent_process(pipe_conn):
    try:
        t = Thread(target=auth_daemon, daemon=True)
        t.start()

        def heartbeat_thread(pipe):
            while True:
                try:
                    pipe.send("AGENT_PULSE")
                    time.sleep(1)
                except (IOError, EOFError):
                    print("CRITICAL: Guardian process disconnected!",
                          file=sys.stderr)
                    emergency_self_destruct()
                    os._exit(1)

        hb_thread = Thread(target=heartbeat_thread, args=(pipe_conn,))
        hb_thread.start()

        print("INFO: Main agent process running. Starting Gunicorn server...")

        gunicorn_command = [
            sys.executable,
            "-m", "gunicorn",
            "-w", "3",
            "-b", "0.0.0.0:8000",
            "--chdir", ".",
            "src.server.server:app"
        ]

        process = subprocess.run(gunicorn_command)

        print(
            f"INFO: Gunicorn process terminated with code {process.returncode}.",
            file=sys.stderr)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"FATAL ERROR IN AGENT PROCESS: {e}", file=sys.stderr)

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

            else:
                if time.time() - last_pulse_time > 5:
                    print(
                        "CRITICAL: Main agent process is unresponsive! Initiating self-destruct",
                        file=sys.stderr)
                    emergency_self_destruct()
                    break

            if not check_parent():
                print(
                    "INFO: Main launcher process is gone. Guardian is shutting down",
                    file=sys.stderr)
                break

            time.sleep(1)

        except (IOError, EOFError):
            print(
                "CRITICAL: Communication pipe broke. Main agent is dead. Initiating self-destruct",
                file=sys.stderr)
            emergency_self_destruct()
            break

def main_launcher():
    parent_conn, child_conn = Pipe()

    guardian = Process(target=run_guardian_process, args=(child_conn, os.getpid()))
    guardian.daemon = True
    guardian.start()

    while True:
        agent = Process(target=run_agent_process, args=(parent_conn, ))
        agent.start()
        print(f"INFO: Agent process started with PID {agent.pid}")
        agent.join()

        if guardian.is_alive():
            print("WARNING: Main agent process terminated. Restarting ...", file=sys.stderr)
            time.sleep(3)
        else:
            print("CRITICAL: Both agents proccesses have terminated. Shutting down launcher", file=sys.stderr)
            break


if __name__ == "__main__":
    is_agent_mode = "type=agent" in sys.argv
    if is_agent_mode:
        main_launcher()
    else:
        cli()

    # args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)
    # mode = args.get("type")
    #
    # if mode == "agent":
    #
    #     # TODO: enable on prod
    #     # ignored = [signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT]
    #     # for s in ignored:
    #     #     try:
    #     #         signal.signal(s, signal.SIG_IGN)
    #     #     except Exception:
    #     #         pass
    #
    #     t = Thread(target=auth_daemon, daemon=True)
    #     t.start()
    #     app()
    #
    # elif mode == "cli":
    #     cli()
