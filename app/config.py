"""workspace.toml 解析与校验：缺失字段按默认补齐，未知字段告警不失败。"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class ConfigError(Exception):
    """config.invalid"""


@dataclass
class StorageCfg:
    page_size: int = 4096
    wal_mode: bool = True
    synchronous: str = "NORMAL"
    busy_timeout_ms: int = 5000
    cache_size_kib: int = 65536
    mmap_size_mb: int = 256
    auto_checkpoint_pages: int = 1000
    temp_store: str = "MEMORY"


@dataclass
class RetrievalCfg:
    default_topk: int = 20
    rerank_topk: int = 50
    alpha: float = 0.5
    fusion: str = "score"
    rrf_k: int = 60
    bm25_title_weight: float = 3.0
    bm25_body_weight: float = 1.0
    min_score: float = 0.0
    empty_fallback: str = "original"


@dataclass
class LlmCfg:
    enabled: bool = True
    endpoint: str = ""
    api_key_ref: str = ""
    model: str = "gpt-4o-mini"
    pivot_max_tokens: int = 64
    pivot_temperature: float = 0.2
    merge_enabled: bool = False
    merge_max_tokens: int = 256
    budget_monthly_usd: float = 1.0
    budget_per_query_usd: float = 0.01
    timeout_ms: int = 8000
    fallback: str = "original_bm25"


@dataclass
class ParserCfg:
    pdf_library: str = "pypdf"
    docx_library: str = "python-docx"
    xlsx_library: str = "openpyxl"
    chunk_target_tokens: int = 400
    chunk_overlap_tokens: int = 80
    max_page_per_doc: int = 5000
    encoding: str = "utf-8"
    hash_algorithm: str = "sha256"


@dataclass
class IntegrityCfg:
    mode: str = "chain"
    chain_scope: str = "all"
    hkdf_salt_path: str = "meta/hkdf.salt"
    keyring_label: str = ""
    gcm_nonce_size: int = 12


@dataclass
class NasCfg:
    expected_host: str = ""
    heartbeat_interval_s: int = 30
    detached_cache_max_gib: int = 10
    detached_readonly: bool = True


@dataclass
class WorkspaceConfig:
    schema_version: int = SCHEMA_VERSION
    created_at: str = ""
    workspace_id: str = ""
    name: str = ""
    root_path: str = ""
    description: str = ""
    hidden_dir: str = ".kbengine"
    index_path: str = ""
    warnings: list[str] = field(default_factory=list)
    storage: StorageCfg = field(default_factory=StorageCfg)
    retrieval: RetrievalCfg = field(default_factory=RetrievalCfg)
    llm: LlmCfg = field(default_factory=LlmCfg)
    parser: ParserCfg = field(default_factory=ParserCfg)
    integrity: IntegrityCfg = field(default_factory=IntegrityCfg)
    nas: NasCfg = field(default_factory=NasCfg)

    def to_toml(self) -> str:
        s = self.storage
        r = self.retrieval
        l = self.llm
        p = self.parser
        it = self.integrity
        n = self.nas

        def esc(v: str) -> str:
            return str(v).replace("\\", "\\\\").replace('"', '\\"')

        return f"""schema_version = {self.schema_version}
created_at = "{esc(self.created_at)}"
workspace_id = "{esc(self.workspace_id)}"
name = "{esc(self.name)}"
root_path = "{esc(self.root_path)}"
description = "{esc(self.description)}"
hidden_dir = "{esc(self.hidden_dir)}"
index_path = "{esc(self.index_path)}"

[storage]
page_size = {s.page_size}
wal_mode = {str(s.wal_mode).lower()}
synchronous = "{s.synchronous}"
busy_timeout_ms = {s.busy_timeout_ms}
cache_size_kib = {s.cache_size_kib}
mmap_size_mb = {s.mmap_size_mb}
auto_checkpoint_pages = {s.auto_checkpoint_pages}
temp_store = "{s.temp_store}"

[retrieval]
default_topk = {r.default_topk}
rerank_topk = {r.rerank_topk}
alpha = {r.alpha}
fusion = "{r.fusion}"
rrf_k = {r.rrf_k}
bm25_title_weight = {r.bm25_title_weight}
bm25_body_weight = {r.bm25_body_weight}
min_score = {r.min_score}
empty_fallback = "{r.empty_fallback}"

[llm]
enabled = {str(l.enabled).lower()}
endpoint = "{l.endpoint}"
api_key_ref = "{l.api_key_ref}"
model = "{l.model}"
pivot_max_tokens = {l.pivot_max_tokens}
pivot_temperature = {l.pivot_temperature}
merge_enabled = {str(l.merge_enabled).lower()}
merge_max_tokens = {l.merge_max_tokens}
budget_monthly_usd = {l.budget_monthly_usd}
budget_per_query_usd = {l.budget_per_query_usd}
timeout_ms = {l.timeout_ms}
fallback = "{l.fallback}"

[parser]
pdf_library = "{p.pdf_library}"
docx_library = "{p.docx_library}"
xlsx_library = "{p.xlsx_library}"
chunk_target_tokens = {p.chunk_target_tokens}
chunk_overlap_tokens = {p.chunk_overlap_tokens}
max_page_per_doc = {p.max_page_per_doc}
encoding = "{p.encoding}"
hash_algorithm = "{p.hash_algorithm}"

[integrity]
mode = "{it.mode}"
chain_scope = "{it.chain_scope}"
hkdf_salt_path = "{it.hkdf_salt_path}"
keyring_label = "{it.keyring_label}"
gcm_nonce_size = {it.gcm_nonce_size}

[nas]
expected_host = "{n.expected_host}"
heartbeat_interval_s = {n.heartbeat_interval_s}
detached_cache_max_gib = {n.detached_cache_max_gib}
detached_readonly = {str(n.detached_readonly).lower()}
"""


def _validate(cfg: WorkspaceConfig) -> None:
    if cfg.schema_version != SCHEMA_VERSION:
        raise ConfigError(f"schema.unsupported: version {cfg.schema_version}")
    if cfg.retrieval.fusion not in ("score", "rrf"):
        cfg.warnings.append("fusion 非白名单值，回退 score")
        cfg.retrieval.fusion = "score"
    if not 1 <= cfg.retrieval.rrf_k <= 1000:
        cfg.warnings.append("rrf_k 超范围，回退 60")
        cfg.retrieval.rrf_k = 60
    if not 0 <= cfg.retrieval.alpha <= 1:
        cfg.warnings.append("alpha 超范围，回退 0.5")
        cfg.retrieval.alpha = 0.5
    if cfg.storage.page_size not in (4096, 8192, 16384):
        cfg.warnings.append("page_size 非法，回退 4096")
        cfg.storage.page_size = 4096
    if cfg.index_path:
        try:
            ip = Path(cfg.index_path).resolve()
            rp = Path(cfg.root_path).resolve()
            if rp in ip.parents or ip == rp:
                raise ConfigError("index_path 不可指向工作区子目录")
        except OSError as e:
            raise ConfigError(f"index_path 不可访问: {e}") from e


def load_config(path: Path) -> WorkspaceConfig:
    if not path.exists():
        raise ConfigError(f"workspace.toml 不存在: {path}")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"toml 解析失败: {e}") from e

    known_top = {
        "schema_version", "created_at", "workspace_id", "name", "root_path",
        "description", "hidden_dir", "index_path",
        "storage", "retrieval", "llm", "parser", "integrity", "nas",
    }
    cfg = WorkspaceConfig()
    for k, v in raw.items():
        if k in ("storage", "retrieval", "llm", "parser", "integrity", "nas"):
            sub = getattr(cfg, k)
            for sk, sv in v.items():
                if hasattr(sub, sk):
                    setattr(sub, sk, sv)
                else:
                    cfg.warnings.append(f"未知字段 {k}.{sk}")
        elif k in known_top:
            setattr(cfg, k, v)
        else:
            cfg.warnings.append(f"未知字段 {k}")
    if not cfg.workspace_id:
        cfg.warnings.append("workspace_id 为空")
    _validate(cfg)
    return cfg
