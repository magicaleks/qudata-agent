from src import runtime
from waitress import serve
from src.server.server import app as server_app


def security_daemon() -> None:
    pass

def app() -> None:
    serve(server_app, host="0.0.0.0", port=runtime.agent_port(), threads=3)

def cli() -> None:
    pass
