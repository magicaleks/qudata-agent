from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


@dataclass
class CreateInstance:
    # Docker
    image: str
    image_tag: str

    registry: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None

    # Settings
    env_variables: dict[str, str] = {}
    command: Optional[str] = None
    ports: dict[str, str] = {}
    storage_gb: int

    # Connection
    ssh_enabled: bool = False


@dataclass
class InstanceCreated:
    success: bool
    ports: dict[str, str] = []
    tunnel_host: Optional[str] = None
    tunnel_token: Optional[str] = None


class InstanceAction(StrEnum):
    start = "start"
    stop = "stop"
    restart = "restart"
    delete = "delete"


@dataclass
class ManageInstance:
    action: InstanceAction
