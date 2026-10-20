import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";

/* ---------- 小组件 ---------- */

const STATE_META = {
  normal: { label: "在线", cls: "ok" },
  detached: { label: "已分离", cls: "warn" },
  tampered: { label: "完整性异常", cls: "bad" },
};

function StateBadge({ state, reason }) {
  const m = STATE_META[state] || STATE_META.normal;
  return (
    <span className={`badge badge-${m.cls}`} title={reason || m.label}>
      <i className="dot" />
      {m.label}
    </span>
  );
}

function PivotMark({ size = 44 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 44 44" fill="none" aria-hidden>
      <circle cx="22" cy="22" r="20" stroke="var(--accent)" strokeOpacity=".25" strokeWidth="1.2" />
      <circle cx="22" cy="22" r="13" stroke="var(--accent)" strokeOpacity=".55" strokeWidth="1.2" strokeDasharray="3 4" />
      <circle cx="22" cy="22" r="5.5" fill="var(--accent)" />
      <circle cx="22" cy="2" r="2.2" fill="var(--accent)" />
      <circle cx="41" cy="30" r="1.8" fill="var(--accent)" strokeOpacity=".6" />
      <circle cx="6" cy="34" r="1.4" fill="var(--accent)" strokeOpacity=".4" />
    </svg>
  );
}

function Toast({ msg, kind, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 4200);
    return () => clearTimeout(t);
  }, [onDone]);
  return <div className={`toast toast-${kind}`}>{msg}</div>;
}

function ScoreMeter({ score }) {
  const pct = Math.max(2, Math.min(100, Math.round(score * 100)));
  return (
    <div className="meter" title={`fused = ${score}`}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ---------- 空态：初始化 / 打开工作区 ---------- */

function HubGate({ onReady }) {
  const [tab, setTab] = useState("open");
  const [rootPath, setRootPath] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!rootPath.trim()) return setErr("请输入工作区目录路径");
    setBusy(true);
    try {
      const r =
        tab === "create"
          ? await api.initWorkspace(rootPath.trim(), name.trim() || "新工作区")
          : await api.openWorkspace(rootPath.trim());
      onReady(r.id);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gate">
      <div className="gate-card rise">
        <div className="gate-brand">
          <PivotMark size={56} />
          <div>
            <h1>盘枢</h1>
            <p className="tagline">目录即工作区 · 索引是可再生的副产物</p>
          </div>
        </div>

        <div className="gate-tabs">
          <button className={tab === "open" ? "on" : ""} onClick={() => setTab("open")}>
            打开已有工作区
          </button>
          <button className={tab === "create" ? "on" : ""} onClick={() => setTab("create")}>
            初始化新工作区
          </button>
        </div>

        <form onSubmit={submit} className="gate-form">
          <label>
            <span>工作区目录路径</span>
            <input
              value={rootPath}
              onChange={(e) => setRootPath(e.target.value)}
              placeholder="例如 D:\项目资料"
              spellCheck={false}
            />
          </label>
          {tab === "create" && (
            <label className="fade-in">
              <span>工作区名称</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如 项目资料档案"
              />
            </label>
          )}
          <p className="hint">
            初始化将在该目录下创建隐藏的 <code>.kbengine/</code> 信任锚点，元数据、索引与
            Merkle 完整性链全部落在其中，目录可整体复制迁移。
          </p>
          {err && <p className="err">{err}</p>}
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "处理中…" : tab === "create" ? "初始化并打开" : "打开"}
          </button>
        </form>
      </div>
    </div>
  );
}

/* ---------- 检索视图 ---------- */

function RouteTag({ route }) {
  const map = { original: "原始", pivot: "连接词", both: "双路命中" };
  return <span className={`route-tag route-${route}`}>{map[route] || route}</span>;
}

function SearchView({ ws, detail }) {
  const [query, setQuery] = useState("");
  const [usePivot, setUsePivot] = useState(true);
  const [alpha, setAlpha] = useState(detail?.config?.retrieval?.alpha ?? 0.5);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const inputRef = useRef(null);

  const doSearch = async (e) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.retrieve(ws.workspace_id, { query, use_pivot: usePivot, alpha });
      setRes(r);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="view">
      <form className={`searchbox ${busy ? "busy" : ""}`} onSubmit={doSearch}>
        <svg className="search-ic" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="在知识库中检索…"
          spellCheck={false}
          autoFocus
        />
        <button className="btn btn-primary" disabled={busy || !query.trim()}>
          {busy ? "检索中" : "检索"}
        </button>
      </form>

      <div className="search-opts">
        <label className="switch">
          <input type="checkbox" checked={usePivot} onChange={(e) => setUsePivot(e.target.checked)} />
          <span>LLM 连接词第二路召回</span>
        </label>
        <label className="range">
          <span>α = {alpha.toFixed(2)}</span>
          <input type="range" min="0" max="1" step="0.05" value={alpha}
            onChange={(e) => setAlpha(parseFloat(e.target.value))} />
        </label>
      </div>

      {res && (
        <div className="search-meta fade-in">
          {res.pivots?.length > 0 && (
            <div className="pivots">
              <span className="pivots-label">连接词</span>
              {res.pivots.map((p) => (
                <span key={p} className="chip" onClick={() => { setQuery(p); }}>{p}</span>
              ))}
            </div>
          )}
          <div className="search-stats mono">
            双路候选 {res.routes?.original ?? 0} / {res.routes?.pivot ?? 0}
            {res.degraded && <em className="degraded">已降级 · {res.reason || "单路 BM25"}</em>}
          </div>
        </div>
      )}

      {err && <p className="err">检索失败：{err}</p>}

      {res && res.results.length === 0 && !err && (
        <div className="empty-results fade-in">
          <p>没有找到匹配的切片。</p>
          <p className="hint">建议拆分关键词、去掉停用词，或使用更专有的名词。</p>
        </div>
      )}

      <div className="results">
        {res?.results?.map((r, i) => (
          <article key={r.chunk_id} className="result-card rise" style={{ animationDelay: `${i * 40}ms` }}>
            <header>
              <RouteTag route={r.route} />
              <span className="mono path">{r.rel_path}</span>
              {r.page_start != null && <span className="mono page">p.{r.page_start}</span>}
              <ScoreMeter score={r.score} />
              <span className="mono score">{r.score.toFixed(4)}</span>
            </header>
            {r.title && <h3>{r.title}</h3>}
            <p className="snippet">{r.snippet}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

/* ---------- 文档视图 ---------- */

function DocsView({ ws, reload }) {
  const [docs, setDocs] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.documents(ws.workspace_id);
      setDocs(r.documents);
    } catch {
      setDocs([]);
    }
  }, [ws.workspace_id]);

  useEffect(() => { load(); }, [load]);

  const doScan = async () => {
    setBusy(true);
    try {
      await api.scan(ws.workspace_id);
      await api.index(ws.workspace_id);
      await load();
      reload();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (docId) => {
    if (!confirm("确认删除该文档及其全部切片？")) return;
    await api.deleteDoc(ws.workspace_id, docId);
    await load();
    reload();
  };

  const STATUS = { pending: "待索引", indexing: "索引中", ready: "就绪", failed: "失败", skipped: "跳过" };

  return (
    <div className="view">
      <div className="view-head">
        <h2>文档索引</h2>
        <button className="btn btn-primary" onClick={doScan} disabled={busy}>
          {busy ? "扫描并索引中…" : "扫描目录并建索引"}
        </button>
      </div>
      {!docs ? (
        <p className="hint">加载中…</p>
      ) : docs.length === 0 ? (
        <p className="hint">工作区还没有登记任何文档，点击右上角「扫描目录并建索引」。</p>
      ) : (
        <table className="docs-table">
          <thead>
            <tr>
              <th>路径</th><th>状态</th><th>页数</th><th>解析器</th><th>大小</th><th></th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.doc_id}>
                <td className="mono path">{d.rel_path}</td>
                <td><span className={`st st-${d.status}`}>{STATUS[d.status] || d.status}</span></td>
                <td className="mono">{d.page_count ?? "—"}</td>
                <td className="mono dim">{d.parser_version || "—"}</td>
                <td className="mono dim">{(d.size_bytes / 1024).toFixed(1)} KB</td>
                <td>
                  <button className="btn-ghost" onClick={() => doDelete(d.doc_id)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- 完整性视图 ---------- */

function IntegrityView({ ws, reload }) {
  const [head, setHead] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.chain(ws.workspace_id).then(setHead).catch(() => setHead(null));
  }, [ws.workspace_id]);

  const doVerify = async () => {
    setVerifying(true);
    setResult(null);
    try {
      const r = await api.verify(ws.workspace_id);
      setResult({ ok: true, ...r });
      reload();
    } catch (e) {
      setResult({ ok: false, message: e.message });
      reload();
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="view">
      <div className="view-head">
        <h2>完整性 · Merkle 链</h2>
        <button className="btn btn-primary" onClick={doVerify} disabled={verifying}>
          {verifying ? "校验中…" : "立即校验"}
        </button>
      </div>
      <div className="cards-2">
        <div className="stat-card">
          <span className="stat-label">链头 seq</span>
          <span className="stat-value mono">{head?.seq ?? "—"}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">链头哈希</span>
          <span className="stat-value mono hash">{head?.hash?.slice(0, 24) || "—"}…</span>
        </div>
      </div>
      {result && (
        <p className={`verify-result ${result.ok ? "ok" : "bad"} fade-in`}>
          {result.ok ? `校验通过：${result.records} 条链记录完整。` : `校验失败：${result.message}`}
        </p>
      )}
      <p className="hint">
        链只证明 <code>.kbengine/</code> 内被记录的状态未被篡改；校验失败将进入 Tampered
        只读态，禁止写索引与导出。WAL/SHM 残留由 SQLite checkpoint 自动回收，请勿手动删除
        <code>-wal</code> 文件。
      </p>
    </div>
  );
}

/* ---------- 预算视图 ---------- */

function BudgetView({ ws }) {
  const [b, setB] = useState(null);
  useEffect(() => {
    api.budget(ws.workspace_id).then(setB).catch(() => setB(null));
  }, [ws.workspace_id]);
  const LABEL = { daily: "今日", monthly: "本月", total: "累计" };
  return (
    <div className="view">
      <div className="view-head"><h2>LLM 预算</h2></div>
      {!b ? <p className="hint">尚无调用记录。连接词命中缓存时零成本。</p> : (
        <div className="cards-3">
          {Object.entries(b).map(([k, v]) => (
            <div key={k} className="stat-card">
              <span className="stat-label">{LABEL[k] || k}</span>
              <span className="stat-value mono">${v.cost_usd.toFixed(4)}</span>
              <span className="stat-sub mono">{v.requests} 次调用</span>
              {v.limit_usd > 0 && v.limit_usd < 1e8 && (
                <div className="meter"><span style={{ width: `${Math.min(100, (v.cost_usd / v.limit_usd) * 100)}%` }} /></div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- 设置视图 ---------- */

function SettingsView({ ws, detail, reload }) {
  const llmCfg = detail?.config?.llm || {};
  const [endpoint, setEndpoint] = useState(llmCfg.endpoint || "");
  const [model, setModel] = useState(llmCfg.model || "gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [test, setTest] = useState(null);
  const [mcp, setMcp] = useState(null);
  useEffect(() => {
    setEndpoint(llmCfg.endpoint || "");
    setModel(llmCfg.model || "gpt-4o-mini");
  }, [llmCfg.endpoint, llmCfg.model]);
  useEffect(() => {
    api.mcp().then(setMcp).catch(() => setMcp(null));
  }, []);
  const doTest = async () => {
    setTest("testing");
    try {
      const r = await api.llmTest({ endpoint, model, api_key: apiKey });
      setTest(r);
    } catch (e) {
      setTest({ ok: false, reason: e.message });
    }
  };
  return (
    <div className="view">
      <div className="view-head"><h2>LLM 接入</h2></div>
      <div className="cards-2 form-grid">
        <label>
          <span>OpenAI 协议端点</span>
          <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)}
            placeholder="https://api.openai.com/v1" spellCheck={false} />
        </label>
        <label>
          <span>模型</span>
          <input value={model} onChange={(e) => setModel(e.target.value)} spellCheck={false} />
        </label>
        <label>
          <span>API Key（仅内存，不落盘）</span>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-…" spellCheck={false} />
        </label>
        <div className="form-actions">
          <button className="btn" onClick={doTest}>连通测试</button>
        </div>
      </div>
      {test && test !== "testing" && (
        <p className={`verify-result ${test.ok ? "ok" : "bad"} fade-in mono`}>
          {test.ok ? `连通成功 · ${test.latency_ms}ms · 示例连接词: ${(test.pivots || []).join("、") || "—"}` : `失败：${test.reason}`}
        </p>
      )}
      <p className="hint">
        联网只发生在用户明确配置的 LLM 端点，且只发送 query 与候选合并片段；原始文档与切片正文默认不出机。
        明文密钥禁止写入 <code>workspace.toml</code>。
      </p>

      <div className="mcp-card">
        <div className="mcp-head">
          <h3>MCP · 本地 Agent 接口</h3>
          <span className={`badge ${mcp?.enabled ? "badge-ok" : "badge-warn"}`}>
            <i className="dot" />
            {mcp?.enabled ? "端口已开放" : "stdio 模式"}
          </span>
        </div>
        {mcp?.enabled ? (
          <>
            <p className="hint">Streamable HTTP 端点（仅本机回环）：</p>
            <code className="mcp-url">{mcp.url}</code>
          </>
        ) : (
          <p className="hint">当前未开放 HTTP 端口，可使用 stdio 方式接入：</p>
        )}
        <p className="hint" style={{ marginTop: 10 }}>stdio 启动命令：</p>
        <code className="mcp-url">{mcp?.stdio_command || "Panhub.exe mcp"}</code>
        <div className="mcp-tools">
          {(mcp?.tools || []).map((t) => (
            <span key={t} className="mcp-tool">{t}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---------- 主布局 ---------- */

const NAV = [
  { key: "search", label: "检索", icon: "M11 3a8 8 0 1 0 4.9 14.3L21 22" },
  { key: "docs", label: "文档", icon: "M6 2h9l5 5v15H6zM14 2v6h6" },
  { key: "integrity", label: "完整性", icon: "M12 2 4 6v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6z" },
  { key: "budget", label: "预算", icon: "M3 7h18v12H3zM3 7l2-4h14l2 4M12 11v6M9 14h6" },
  { key: "settings", label: "设置", icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12" },
];

export default function App() {
  const [wsList, setWsList] = useState([]);
  const [current, setCurrent] = useState(null);
  const [detail, setDetail] = useState(null);
  const [view, setView] = useState("search");
  const [toast, setToast] = useState(null);

  const loadDetail = useCallback(async (ws) => {
    if (!ws) return setDetail(null);
    try {
      setDetail(await api.workspace(ws.id));
    } catch {
      setDetail(null);
    }
  }, []);

  useEffect(() => {
    api.listWorkspaces().then((r) => {
      setWsList(r.workspaces);
      if (r.workspaces.length && !current) setCurrent(r.workspaces[0]);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { loadDetail(current); }, [current, loadDetail]);

  if (!current) return <HubGate onReady={async (id) => {
    const r = await api.listWorkspaces();
    setWsList(r.workspaces);
    const ws = r.workspaces.find((w) => w.id === id);
    setCurrent(ws || r.workspaces[0] || null);
  }} />;

  const st = detail?.state || current.state;
  const readonly = st !== "normal";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <PivotMark />
          <div>
            <h1>盘枢</h1>
            <span className="brand-sub mono">KBEngine v1.0</span>
          </div>
        </div>

        <div className="ws-card">
          <div className="ws-card-head">
            <span className="ws-name">{detail?.name || current.name}</span>
            <StateBadge state={st} reason={detail?.stats?.reason} />
          </div>
          <p className="mono ws-root" title={current.root_path}>{current.root_path}</p>
          {detail?.stats && (
            <div className="ws-stats mono">
              <span>{detail.stats.docs} 文档</span>
              <span>{detail.stats.chunks} 切片</span>
              <span>{detail.stats.ready} 就绪</span>
            </div>
          )}
        </div>

        <nav className="nav">
          {NAV.map((n, i) => (
            <button key={n.key} className={view === n.key ? "on" : ""}
              onClick={() => setView(n.key)} style={{ animationDelay: `${i * 50}ms` }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d={n.icon} />
              </svg>
              {n.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <button className="btn-ghost" onClick={async () => {
            await api.closeWorkspace(current.id);
            const r = await api.listWorkspaces();
            setWsList(r.workspaces);
            setCurrent(r.workspaces[0] || null);
            if (!r.workspaces.length) setCurrent(null);
          }}>关闭工作区</button>
        </div>
      </aside>

      <main className="main">
        {view === "search" && <SearchView ws={current} detail={detail} />}
        {view === "docs" && <DocsView ws={current} reload={() => loadDetail(current)} />}
        {view === "integrity" && <IntegrityView ws={current} reload={() => loadDetail(current)} />}
        {view === "budget" && <BudgetView ws={current} />}
        {view === "settings" && <SettingsView ws={current} detail={detail} reload={() => loadDetail(current)} />}
        {readonly && (
          <div className={`readonly-ribbon ${st}`}>
            {st === "detached" ? "工作区处于分离态：只读检索可用，写索引被挂起。" : "完整性异常：只读浏览可用，写索引与导出已禁用。"}
          </div>
        )}
      </main>

      {toast && <Toast msg={toast.msg} kind={toast.kind} onDone={() => setToast(null)} />}
    </div>
  );
}
