"""三态机：Normal / Detached / Tampered，状态落 workspace_state 表。"""
from __future__ import annotations

import sqlite3
import time

VALID = ("normal", "detached", "tampered")


class StateMachine:
    def __init__(self, workspace_id: str, conn: sqlite3.Connection):
        self.workspace_id = workspace_id
        self.conn = conn
        self.state = "normal"
        self.reason = ""
        row = conn.execute(
            "SELECT state, reason FROM workspace_state WHERE workspace_id=?",
            (workspace_id,),
        ).fetchone()
        if row:
            self.state, self.reason = row["state"], row["reason"]
        else:
            self._persist("normal", "")

    def _persist(self, state: str, reason: str) -> None:
        self.conn.execute(
            "INSERT INTO workspace_state(workspace_id,state,reason,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(workspace_id) DO UPDATE SET state=excluded.state, reason=excluded.reason, "
            "updated_at=excluded.updated_at",
            (self.workspace_id, state, reason, int(time.time())),
        )
        self.conn.commit()

    def set_state(self, state: str, reason: str = "") -> None:
        if state not in VALID:
            raise ValueError(f"非法状态: {state}")
        self.state = state
        self.reason = reason
        self._persist(state, reason)

    def can_write(self) -> bool:
        return self.state == "normal"

    def can_export(self) -> bool:
        return self.state != "tampered"

    def snapshot(self) -> dict:
        return {"state": self.state, "reason": self.reason}
