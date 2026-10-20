/* 受限 IPC 桥：白名单暴露，禁用 nodeIntegration。 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("panhub", {
  pickDirectory: () => ipcRenderer.invoke("pick-directory"),
  onBackendReady: (cb) => ipcRenderer.on("backend-ready", (_e, port) => cb(port)),
});
