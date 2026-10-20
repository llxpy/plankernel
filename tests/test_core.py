"""核心链路测试：初始化/锁/索引/检索/链校验/篡改检测。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.index.service import index_documents, scan_documents
from app.retrieval.engine import retrieve
from app.retrieval.normalize import build_match_query, normalize
from app.workspace import anchor as anchor_mod
from app.workspace.anchor import AnchorMismatch
from app.workspace.locking import WorkspaceLocked, acquire_lock
from app.workspace.manager import WorkspaceRegistry


@pytest.fixture()
def ws_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


def test_init_and_open(ws_root: Path):
    ws_root.mkdir()
    cfg = anchor_mod.initialize(ws_root, "测试工作区")
    assert (ws_root / ".kbengine" / "workspace.toml").exists()
    reg = WorkspaceRegistry()
    ws = reg.open(ws_root)
    assert ws.workspace_id == cfg.workspace_id
    assert ws.state.state == "normal"
    reg.shutdown()


def test_lock_mutual_exclusion(ws_root: Path):
    ws_root.mkdir()
    anchor_mod.initialize(ws_root, "锁测试")
    hidden = ws_root / ".kbengine"
    lock1 = acquire_lock(hidden, "ws-a")
    with pytest.raises(WorkspaceLocked):
        acquire_lock(hidden, "ws-b")
    lock1.release()
    lock2 = acquire_lock(hidden, "ws-b")
    lock2.release()


def test_anchor_mismatch(ws_root: Path):
    ws_root.mkdir()
    anchor_mod.initialize(ws_root, "锚点")
    anchor_mod.verify_anchor(ws_root)  # 一致
    # 模拟迁移：目录移动到新位置（tmp_path 不允许真实移动，改写 anchor）
    hidden = ws_root / ".kbengine"
    f = hidden / "anchor.sha256"
    f.write_text("deadbeef\nsalt=xx\ncreated_at=2026-01-01", encoding="utf-8")
    with pytest.raises(AnchorMismatch):
        anchor_mod.verify_anchor(ws_root)


def test_scan_index_retrieve(ws_root: Path):
    ws_root.mkdir()
    (ws_root / "notes.txt").write_text(
        "服务器频繁重启的故障排查记录。2026年3月，机房断电导致宕机，日志显示内存溢出。\n"
        "解决方案：更换电源模块并升级内存。", encoding="utf-8")
    (ws_root / "contract.txt").write_text(
        "2026年交付合同：乙方须于6月30日前完成软件交付，违约方需支付合同金额10%的违约赔偿金。",
        encoding="utf-8")
    anchor_mod.initialize(ws_root, "检索测试")
    reg = WorkspaceRegistry()
    ws = reg.open(ws_root)

    scan = scan_documents(ws)
    assert scan["added"] == 2
    idx = index_documents(ws)
    assert idx["indexed"] == 2 and idx["failed"] == 0
    assert ws.stats()["chunks"] >= 2

    r = retrieve(ws, "服务器重启 故障", use_pivot=False)
    assert r["results"], "检索应命中结果"
    assert r["results"][0]["rel_path"].endswith("notes.txt")

    r2 = retrieve(ws, "违约赔偿", use_pivot=False)
    assert r2["results"]
    assert r2["results"][0]["rel_path"].endswith("contract.txt")
    reg.shutdown()


def test_chain_verify_and_tamper(ws_root: Path):
    ws_root.mkdir()
    anchor_mod.initialize(ws_root, "完整性")
    reg = WorkspaceRegistry()
    ws = reg.open(ws_root)
    ws.chain.append("docs", "t1", {"a": 1})
    ws.chain.append("docs", "t2", {"a": 2})
    assert ws.chain.verify()["ok"] is True

    # 篡改 payload
    conn = ws.chain_db.connect()
    conn.execute("UPDATE integrity_chain SET payload_hash='f' WHERE seq=1")
    conn.commit()
    from app.integrity.chain import ChainCorrupt

    with pytest.raises(ChainCorrupt):
        ws.chain.verify()
    reg.shutdown()


def test_normalize_and_match():
    q, terms = normalize("　服务器 频繁重启！FF01ｗ")
    assert "ｗ" not in q and "w" in q
    m = build_match_query(["合同 违约"])
    assert '"违约"' in m and '"合同"' in m  # jieba 细粒度切词
