import sys
import time
from pathlib import Path
from typing import Final

from docparser.config import get_settings

MAX_HEARTBEAT_AGE_SECONDS: Final[float] = 30.0


def is_alive(
    heartbeat_path: Path, max_age_seconds: float = MAX_HEARTBEAT_AGE_SECONDS
) -> bool:
    try:
        age = time.time() - heartbeat_path.stat().st_mtime
    except FileNotFoundError:
        return False
    return age <= max_age_seconds


if __name__ == "__main__":
    sys.exit(0 if is_alive(get_settings().worker_heartbeat_path) else 1)
