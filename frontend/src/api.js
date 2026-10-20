const BASE = "";

async function req(path, options = {}) {
  const res = await fetch(`/api/v1${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data?.error || {};
    throw new Error(`${err.code || res.status}: ${err.message || "请求失败"}`);
  }
  return data;
}

export const api = {
  health: () => req("/healthz"),
  listWorkspaces: () => req("/workspaces"),
  openWorkspace: (root_path, force = false) =>
    req("/workspaces/open", { method: "POST", body: JSON.stringify({ root_path, force }) }),
  initWorkspace: (root_path, name) =>
    req("/workspaces/init", { method: "POST", body: JSON.stringify({ root_path, name }) }),
  workspace: (id) => req(`/workspaces/${id}`),
  closeWorkspace: (id) => req(`/workspaces/${id}/close`, { method: "POST" }),
  verify: (id) => req(`/workspaces/${id}/verify`, { method: "POST" }),
  documents: (id) => req(`/workspaces/${id}/documents`),
  scan: (id, force = false) =>
    req(`/workspaces/${id}/documents/scan`, { method: "POST", body: JSON.stringify({ force }) }),
  index: (id, doc_ids = []) =>
    req(`/workspaces/${id}/documents/index`, { method: "POST", body: JSON.stringify({ doc_ids }) }),
  deleteDoc: (id, docId) => req(`/workspaces/${id}/documents/${docId}`, { method: "DELETE" }),
  retrieve: (id, body) =>
    req(`/workspaces/${id}/retrieval`, { method: "POST", body: JSON.stringify(body) }),
  budget: (id) => req(`/workspaces/${id}/budget`),
  chain: (id) => req(`/workspaces/${id}/chain`),
  llmTest: (body) => req("/llm/test", { method: "POST", body: JSON.stringify(body) }),
};
