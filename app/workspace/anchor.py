"""工作区锚点与初始化：anchor.sha256 绑定 root_path + created_at + salt。"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import WorkspaceConfig

HIDDEN_DIR = ".kbengine"
ANCHOR_FILE = "anchor.sha256"


def anchor_value(root_path: str, created_at: str, salt: str) -> str:
    return hashlib.sha256(f"{root_path}|{created_at}|{salt}".encode()).hexdigest()


def set_hidden_attrib(path: Path) -> None:
    try:
        import ctypes

        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
    except (ImportError, AttributeError, OSError):
        pass


class AnchorMismatch(Exception):
    """workspace.anchor_mismatch"""


class WorkspaceNotInitialized(Exception):
    """workspace.not_found"""


def initialize(root: Path, name: str, description: str = "") -> WorkspaceConfig:
    root = root.resolve()
    if not root.is_dir():
        raise WorkspaceNotInitialized(f"目录不存在: {root}")
    hidden = root / HIDDEN_DIR
    if hidden.exists() and (hidden / "workspace.toml").exists():
        raise FileExistsError("工作区已初始化")
    hidden.mkdir(parents=True, exist_ok=True)
    for sub in ("meta", "index", "cache/parse", "cache/pivot", "tmp", "export", "logs", "lock"):
        (hidden / sub).mkdir(parents=True, exist_ok=True)
    set_hidden_attrib(hidden)

    from app.config import WorkspaceConfig as Cfg
    cfg = Cfg()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    cfg.workspace_id = f"kb-{uuid.uuid4()}"
    cfg.created_at = now
    cfg.name = name
    cfg.root_path = str(root)
    cfg.description = description

    salt = secrets.token_hex(16)
    anchor = anchor_value(str(root), now, salt)
    (hidden / ANCHOR_FILE).write_text(anchor + "\nsalt=" + salt + "\ncreated_at=" + now, encoding="utf-8")
    (hidden / "workspace.toml").write_text(cfg.to_toml(), encoding="utf-8")
    return cfg


def read_anchor(hidden: Path) -> tuple[str, str, str]:
    f = hidden / ANCHOR_FILE
    if not f.exists():
        raise WorkspaceNotInitialized("锚点文件缺失")
    lines = f.read_text(encoding="utf-8").strip().splitlines()
    val = lines[0].strip()
    salt = ""
    created = ""
    for ln in lines[1:]:
        if ln.startswith("salt="):
            salt = ln[5:].strip()
        elif ln.startswith("created_at="):
            created = ln[11:].strip()
    return val, salt, created


def verify_anchor(root: Path) -> str:
    hidden = root / HIDDEN_DIR
    val, salt, created = read_anchor(hidden)
    expected = anchor_value(str(root.resolve()), created, salt)
    if val != expected:
        raise AnchorMismatch("锚点与根路径不一致，需执行重映射")
    return val


def remap_anchor(root: Path) -> None:
    """迁移后重写锚点：保留 salt 与 created_at，只更新 root_path 部分。"""
    hidden = root / HIDDEN_DIR
    _, salt, created = read_anchor(hidden)
    val = anchor_value(str(root.resolve()), created, salt)
    (hidden / ANCHOR_FILE).write_text(
        val + f"\nsalt={salt}\ncreated_at={created}", encoding="utf-8"
    )
