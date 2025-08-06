"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const path = __importStar(require("path"));
const environmentService_1 = require("./services/environmentService");
const downloadService_1 = require("./services/downloadService");
const pythonService_1 = require("./services/pythonService");
const gitService_1 = require("./services/gitService");
let mainWindow = null;
function createWindow() {
    mainWindow = new electron_1.BrowserWindow({
        width: 1600,
        height: 900,
        minWidth: 800,
        minHeight: 600,
        icon: path.join(__dirname, '../src/assets/AUTO_MAA.ico'),
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
        autoHideMenuBar: true,
    });
    mainWindow.setMenuBarVisibility(false);
    const devServer = process.env.VITE_DEV_SERVER_URL;
    if (devServer) {
        mainWindow.loadURL(devServer);
    }
    else {
        const indexHtmlPath = path.join(electron_1.app.getAppPath(), 'dist', 'index.html');
        mainWindow.loadFile(indexHtmlPath);
    }
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
    // 设置各个服务的主窗口引用
    if (mainWindow) {
        (0, downloadService_1.setMainWindow)(mainWindow);
        (0, pythonService_1.setMainWindow)(mainWindow);
        (0, gitService_1.setMainWindow)(mainWindow);
    }
}
// IPC处理函数
electron_1.ipcMain.handle('open-dev-tools', () => {
    if (mainWindow) {
        mainWindow.webContents.openDevTools({ mode: 'undocked' });
    }
});
electron_1.ipcMain.handle('select-folder', async () => {
    if (!mainWindow)
        return null;
    const result = await electron_1.dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory'],
        title: '选择文件夹',
    });
    return result.canceled ? null : result.filePaths[0];
});
electron_1.ipcMain.handle('select-file', async (event, filters = []) => {
    if (!mainWindow)
        return null;
    const result = await electron_1.dialog.showOpenDialog(mainWindow, {
        properties: ['openFile'],
        title: '选择文件',
        filters: filters.length > 0 ? filters : [{ name: '所有文件', extensions: ['*'] }],
    });
    return result.canceled ? null : result.filePaths[0];
});
// 环境检查
electron_1.ipcMain.handle('check-environment', async () => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, environmentService_1.checkEnvironment)(appRoot);
});
// Python相关
electron_1.ipcMain.handle('download-python', async (event, mirror = 'tsinghua') => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, pythonService_1.downloadPython)(appRoot, mirror);
});
electron_1.ipcMain.handle('install-dependencies', async (event, mirror = 'tsinghua') => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, pythonService_1.installDependencies)(appRoot, mirror);
});
electron_1.ipcMain.handle('start-backend', async () => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, pythonService_1.startBackend)(appRoot);
});
// Git相关
electron_1.ipcMain.handle('download-git', async () => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, gitService_1.downloadGit)(appRoot);
});
electron_1.ipcMain.handle('clone-backend', async (event, repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git') => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, gitService_1.cloneBackend)(appRoot, repoUrl);
});
electron_1.ipcMain.handle('update-backend', async (event, repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git') => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, gitService_1.cloneBackend)(appRoot, repoUrl); // 使用相同的逻辑，会自动判断是pull还是clone
});
// 应用生命周期
electron_1.app.whenReady().then(createWindow);
electron_1.app.on('window-all-closed', () => {
    if (process.platform !== 'darwin')
        electron_1.app.quit();
});
electron_1.app.on('activate', () => {
    if (mainWindow === null)
        createWindow();
});
