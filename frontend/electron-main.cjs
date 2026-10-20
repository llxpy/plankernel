/* Electron 主进程：启动并守护 FastAPI 后端子进程，动态端口 + 健康探测。 */
const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

const isDev = !app.isPackaged;
let backend = null;
let backendPort = 7869;
let mainWindow = null;

function resolveBackendCommand() {
  if (isDev) {
    return { cmd: "uv", args: ["run", "python", "-m", "app", "server", "--port", "7869"], cwd: path.join(__dirname, "..") };
  }
  const exe = path.join(process.resourcesPath, "engine", "panhub-engine.exe");
  return { cmd: exe, args: ["server", "--port", "0"], cwd: path.dirname(exe) };
}

function probeHealth(port, timeoutMs = 45000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const r = http.get(`http://127.0.0.1:${port}/api/v1/healthz`, (res) => {
        res.resume();
        resolve(port);
      });
      r.on("error", () => {
        if (Date.now() - start > timeoutMs) return reject(new Error("后端健康探测超时（45s）"));
        setTimeout(attempt, 500);
      });
    };
    attempt();
  });
}

async function startBackend(win) {
  const { cmd, args, cwd } = resolveBackendCommand();
  backend = spawn(cmd, args, { cwd, windowsHide: true });
  backend.stdout.on("data", (d) => {
    const m = String(d).match(/LISTENING port=(\d+)/);
    if (m) backendPort = parseInt(m[1], 10);
  });
  backend.stderr.on("data", (d) => console.error("[backend]", String(d)));
  try {
    await probeHealth(backendPort);
    win.webContents.send("backend-ready", backendPort);
  } catch (e) {
    dialog.showErrorBox("盘枢启动失败", String(e.message || e));
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    backgroundColor: "#0c0c10",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  if (isDev) {
    mainWindow.loadURL("http://127.0.0.1:5180");
  } else {
    mainWindow.loadFile(path.join(__dirname, "dist", "index.html"));
  }
  startBackend(mainWindow);
}

ipcMain.handle("pick-directory", async () => {
  const r = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
  return r.canceled ? null : r.filePaths[0];
});

app.whenReady().then(createWindow);

app.on("window-all-closed", () => app.quit());

app.on("before-quit", () => {
  if (backend) {
    try { backend.kill(); } catch { /* ignore */ }
  }
});
