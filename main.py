import sys

from src.agent import agent, cli, security_daemon

if __name__ == '__main__':
    args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)
    mode = args.get("type")

    if mode == "agent":
        agent()
        security_daemon()
    elif mode == "cli":
        cli()
