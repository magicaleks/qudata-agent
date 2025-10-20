from enum import StrEnum

class InstanceStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    rebooting = "rebooting"
    error = "error"
    destroyed = "destroyed"