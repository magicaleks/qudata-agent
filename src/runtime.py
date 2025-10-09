from functools import lru_cache

from src.utils.ports import get_free_port


@lru_cache
def agent_port() -> int:
    return get_free_port()

@lru_cache
def agent_address() -> str:
    pass
