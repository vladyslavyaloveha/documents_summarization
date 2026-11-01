import os
import time
from pathlib import Path

from docparser.worker.healthcheck import is_alive


def test_missing_heartbeat_is_not_alive(tmp_path: Path) -> None:
    assert not is_alive(tmp_path / "heartbeat")


def test_fresh_heartbeat_is_alive(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat"
    heartbeat.touch()

    assert is_alive(heartbeat)


def test_stale_heartbeat_is_not_alive(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat"
    heartbeat.touch()
    two_minutes_ago = time.time() - 120
    os.utime(heartbeat, (two_minutes_ago, two_minutes_ago))

    assert not is_alive(heartbeat, max_age_seconds=30)
