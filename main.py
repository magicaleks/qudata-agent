# import signal
import sys
from threading import Thread

from src.agent import app, cli
from src.security.auth_daemon import auth_daemon

if __name__ == "__main__":
    args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)
    mode = args.get("type")

    if mode == "agent":

        # TODO: enable on prod
        # ignored = [signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT]
        # for s in ignored:
        #     try:
        #         signal.signal(s, signal.SIG_IGN)
        #     except Exception:
        #         pass

        t = Thread(target=auth_daemon, daemon=True)
        t.start()
        app()

    elif mode == "cli":
        cli()
