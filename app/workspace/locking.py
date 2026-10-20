"""跨进程排他锁：Windows 用 msvcrt LK_NBLCK 非阻塞加锁，POSIX 用 fcntl。"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

LOCK_TIMEOUT_AGE = 30 * 60  # 30 分钟


class WorkspaceLocked(Exception):
    """workspace.locked"""

    def __init__(self, holder: dict):
        self.holder = holder
        super().__init__(f"工作区被其他进程锁定: {holder}")


@dataclass
class DirLock:
    fd: int
    path: Path

    def release(self) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            os.close(self.fd)
            try:
                (self.path.parent / "lock.json").unlink(missing_ok=True)
            except OSError:
                pass


def _read_holder(lockf: Path) -> dict:
    lj = lockf.parent / "lock.json"
    if lj.exists():
        try:
            return json.loads(lj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _holder_is_stale(holder: dict) -> bool:
    pid = holder.get("pid")
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return False
    except OSError:
        pass
    return True


def acquire_lock(hidden: Path, workspace_id: str, force: bool = False) -> DirLock:
    lockdir = hidden / "lock"
    lockdir.mkdir(parents=True, exist_ok=True)
    lockf = lockdir / "workspace.lock"
    fd = os.open(str(lockf), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        holder = _read_holder(lockf)
        if force or _holder_is_stale(holder):
            time.sleep(0.05)
            return acquire_lock(hidden, workspace_id, force=False) if not force else _retry_force(hidden, workspace_id)
        raise WorkspaceLocked(holder) from None
    info = {
        "pid": os.getpid(),
        "start": time.time(),
        "workspace_id": workspace_id,
    }
    (lockdir / "lock.json").write_text(json.dumps(info), encoding="utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, json.dumps(info).encode())
    return DirLock(fd=fd, path=lockf)


def _retry_force(hidden: Path, workspace_id: str) -> DirLock:
    import gc
    import time as _t

    _t.sleep(0.1)
    gc.collect()
    lockdir = hidden / "lock"
    lockf = lockdir / "workspace.lock"
    fd = os.open(str(lockf), os.O_RDWR | os.O_CREAT, 0o600)
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    info = {"pid": os.getpid(), "start": time.time(), "workspace_id": workspace_id}
    (lockdir / "lock.json").write_text(json.dumps(info), encoding="utf-8")
    return DirLock(fd=fd, path=lockf)
