from typing import Final, Optional

import keyring

AGENT_SECRET: Final[str] = "agent-secret"
_KEYRING_SERVICE: Final[str] = "qudata-agent-service"


def _get_password(key: str) -> Optional[str]:
    return keyring.get_password(_KEYRING_SERVICE, key)


def _set_password(key: str, password: str) -> None:
    keyring.set_password(_KEYRING_SERVICE, key, password)


def get_agent_secret() -> str:
    return _get_password(AGENT_SECRET)


def set_agent_secret(secret: str) -> None:
    _set_password(AGENT_SECRET, secret)
