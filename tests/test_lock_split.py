from pathlib import Path

import pytest

from app.workspace import anchor as anchor_mod
from app.workspace.locking import WorkspaceLocked, acquire_lock


@pytest.fixture()
def hidden(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    anchor_mod.initialize(root, "lock split")
    return root / ".kbengine"


def test_lock_acquire_release(hidden: Path):
    lock = acquire_lock(hidden, "a")
    lock.release()


def test_lock_conflict(hidden: Path):
    lock = acquire_lock(hidden, "a")
    with pytest.raises(WorkspaceLocked):
        acquire_lock(hidden, "b")
    lock.release()
