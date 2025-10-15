from pathlib import Path

from src.utils.xlogging import get_logger

logger = get_logger(__name__)
AUTHORIZED_KEYS_PATH = Path("/root/.ssh/authorized_keys")


def _read_keys() -> set[str]:
    if not AUTHORIZED_KEYS_PATH.exists():
        return set()
    try:
        content = AUTHORIZED_KEYS_PATH.read_text(encoding="utf-8")
        return {line.strip() for line in content.splitlines() if line.strip()}
    except IOError as e:
        logger.error(f"Failed to read authorized_keys file: {e}")
        return set()

def _write_keys(keys: set[str]) -> bool:
    try:
        AUTHORIZED_KEYS_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        content = '\n'.join(sorted(list(keys))) + '\n'

        AUTHORIZED_KEYS_PATH.write_text(content, encoding="utf-8")

        AUTHORIZED_KEYS_PATH.chmod(0o600)

        logger.info(f'Succesfully write {len(keys)} keys to authorized_keys')
        return True

    except IOError as e:
        logger.error(f"Failed to write authorized_keys file: {e}")
        return False

def add_ssh_pubkey(pubkey: str) -> bool:
    pubkey = pubkey.strip()
    if not pubkey:
        return False

    logger.info(f"Attempting to add ssh public key: {pubkey[:30]}")
    current_keys = _read_keys()
    if pubkey not in current_keys:
        logger.warning("SSH key already exists")
        return True

    current_keys.add(pubkey)
    return _write_keys(current_keys)

def remove_ssh_pubkey(pubkey: str) -> bool:
    pubkey = pubkey.strip()
    if not pubkey:
        return False

    logger.info(f"Attempting to remove ssh public key: {pubkey[:30]}")
    current_keys = _read_keys()
    if pubkey not in current_keys:
        logger.warning("SSH key not found")
        return True

    current_keys.remove(pubkey)
    return _write_keys(current_keys)

def clear_ssh_keys() -> bool:
    logger.warning("Clearing all ssh keys")
    return _write_keys(set())
