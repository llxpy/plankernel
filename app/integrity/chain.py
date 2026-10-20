"""Merkle 链：SHA-256 哈希链 + AES-256-GCM 状态封装，独立库存储。"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ZERO32 = "0" * 64


def hkdf(master: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    return hashlib.sha256(master + b"|" + salt + b"|" + info).digest()


class ChainCorrupt(Exception):
    """integrity.chain_corrupt"""

    def __init__(self, seq: int, scope: str, detail: str):
        self.seq, self.scope, self.detail = seq, scope, detail
        super().__init__(f"链校验失败 seq={seq} scope={scope}: {detail}")


class MerkleChain:
    def __init__(self, workspace_id: str, conn: sqlite3.Connection, master_key: bytes | None = None):
        self.workspace_id = workspace_id
        self.conn = conn
        self.master = master_key or hashlib.sha256(workspace_id.encode()).digest()

    def _state_key(self, scope: str, salt: bytes = b"kbengine-master") -> bytes:
        return hkdf(self.master, salt, f"{self.workspace_id}|{scope}".encode())

    def latest(self, scope: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM integrity_chain WHERE scope=? ORDER BY seq DESC LIMIT 1", (scope,)
        ).fetchone()

    def append(self, scope: str, scope_key: str, state: dict) -> str:
        prev_row = self.conn.execute(
            "SELECT payload_hash FROM integrity_chain ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev = prev_row["payload_hash"] if prev_row else ZERO32
        canonical = json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        payload_hash = hashlib.sha256(
            f"{scope}|{scope_key}|{prev}|".encode() + canonical.encode()
        ).hexdigest()
        key = self._state_key(scope)
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, canonical.encode(), None)
        self.conn.execute(
            "INSERT INTO integrity_chain(scope,scope_key,prev_hash,payload_hash,state_b64,nonce_b64,level,created_at)"
            " VALUES (?,?,?,?,?,?,0,?)",
            (scope, scope_key, prev, payload_hash,
             base64.b64encode(ct).decode(), base64.b64encode(nonce).decode(), int(time.time())),
        )
        self.conn.commit()
        return payload_hash

    def verify(self, scope: str | None = None, full: bool = False) -> dict:
        q = "SELECT * FROM integrity_chain ORDER BY seq"
        params: tuple = ()
        if scope:
            q = "SELECT * FROM integrity_chain WHERE scope=? ORDER BY seq"
            params = (scope,)
        rows = self.conn.execute(q, params).fetchall()
        prev = ZERO32
        expected_seq = 0
        for r in rows:
            expected_seq += 1
            if r["seq"] != expected_seq:
                raise ChainCorrupt(expected_seq, r["scope"], "seq 不连续")
            key = self._state_key(r["scope"])
            try:
                nonce = base64.b64decode(r["nonce_b64"])
                ct = base64.b64decode(r["state_b64"])
                state = AESGCM(key).decrypt(nonce, ct, None)
            except Exception as e:
                raise ChainCorrupt(r["seq"], r["scope"], f"GCM 解封失败: {e}") from e
            canonical = json.dumps(
                json.loads(state), sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
            expected = hashlib.sha256(
                f"{r['scope']}|{r['scope_key']}|{r['prev_hash']}|".encode() + canonical
            ).hexdigest()
            if expected != r["payload_hash"]:
                raise ChainCorrupt(r["seq"], r["scope"], "payload_hash 不匹配")
            if r["prev_hash"] != prev:
                raise ChainCorrupt(r["seq"], r["scope"], "prev_hash 断裂")
            prev = r["payload_hash"]
        return {"ok": True, "records": expected_seq}

    def head(self) -> dict:
        r = self.conn.execute(
            "SELECT seq, payload_hash FROM integrity_chain ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return {"seq": r["seq"], "hash": r["payload_hash"]} if r else {"seq": 0, "hash": ZERO32}
