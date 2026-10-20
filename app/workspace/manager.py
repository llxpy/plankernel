"""Workspace 运行时对象：锚点校验 + 目录锁 + 双库连接 + 三态机。"""
from __future__ import annotations

import time
from pathlib import Path

from app.config import WorkspaceConfig, load_config
from app.integrity.chain import MerkleChain
from app.storage.database import Database
from app.workspace.anchor import HIDDEN_DIR, AnchorMismatch, verify_anchor
from app.workspace.locking import DirLock, WorkspaceLocked, acquire_lock
from app.workspace.state import StateMachine


class Workspace:
    def __init__(self, root: Path, cfg: WorkspaceConfig, lock: DirLock,
                 db: Database, chain_db: Database, state: StateMachine, chain: MerkleChain):
        self.root = root
        self.cfg = cfg
        self.lock = lock
        self.db = db
        self.chain_db = chain_db
        self.state = state
        self.chain = chain

    @property
    def workspace_id(self) -> str:
        return self.cfg.workspace_id

    @property
    def hidden(self) -> Path:
        return self.root / HIDDEN_DIR

    def close(self) -> None:
        self.db.close()
        self.chain_db.close()
        self.lock.release()

    def stats(self) -> dict:
        conn = self.db.connect()
        docs = conn.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
        chunks = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        ready = conn.execute("SELECT COUNT(*) c FROM docs WHERE status='ready'").fetchone()["c"]
        failed = conn.execute("SELECT COUNT(*) c FROM docs WHERE status='failed'").fetchone()["c"]
        return {
            "docs": docs, "chunks": chunks, "ready": ready, "failed": failed,
            "state": self.state.state, "reason": self.state.reason,
        }


class WorkspaceRegistry:
    """单进程多工作区管理：dict[workspace_id, Workspace]。"""

    def __init__(self):
        self._ws: dict[str, Workspace] = {}

    def list(self) -> list[Workspace]:
        return list(self._ws.values())

    def get(self, workspace_id: str) -> Workspace:
        ws = self._ws.get(workspace_id)
        if ws is None:
            raise KeyError("workspace.not_found")
        return ws

    def has(self, workspace_id: str) -> bool:
        return workspace_id in self._ws

    def open(self, root: Path, force_lock: bool = False) -> Workspace:
        root = root.resolve()
        hidden = root / HIDDEN_DIR
        if not (hidden / "workspace.toml").exists():
            raise FileNotFoundError(f"目录未初始化为工作区: {root}")
        verify_anchor(root)
        cfg = load_config(hidden / "workspace.toml")
        if cfg.workspace_id in self._ws:
            return self._ws[cfg.workspace_id]

        lock = acquire_lock(hidden, cfg.workspace_id, force=force_lock)
        db = Database(hidden / "meta" / "main.db", cfg.storage)
        chain_db = Database(hidden / "meta" / "integrity.db", cfg.storage)
        db.migrate()
        chain_db.migrate()
        state = StateMachine(cfg.workspace_id, db.connect())
        chain = MerkleChain(cfg.workspace_id, chain_db.connect())
        ws = Workspace(root=root, cfg=cfg, lock=lock, db=db, chain_db=chain_db,
                       state=state, chain=chain)
        self._ws[cfg.workspace_id] = ws
        return ws

    def close(self, workspace_id: str) -> None:
        ws = self._ws.pop(workspace_id, None)
        if ws:
            ws.close()

    def shutdown(self) -> None:
        for wid in list(self._ws):
            self.close(wid)
