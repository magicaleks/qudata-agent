import socket

from src.utils.xlogging import get_logger

logger = get_logger(__name__)

def _get_random_port() -> int:
    from random import randint
    return randint(20000, 60000)


def get_free_port() -> int:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        return port
    except Exception as e:
        logger.error(f"Failed to get free port: {e}")
        return _get_random_port()


def get_ports_range(_range: int) -> tuple[int, int]:
    pass
