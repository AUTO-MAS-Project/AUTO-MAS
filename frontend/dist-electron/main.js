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
const fs = __importStar(require("fs"));
const child_process_1 = require("child_process");
const environmentService_1 = require("./services/environmentService");
const downloadService_1 = require("./services/downloadService");
const pythonService_1 = require("./services/pythonService");
const gitService_1 = require("./services/gitService");
// 检查是否以管理员权限运行
function isRunningAsAdmin() {
    try {
        // 在Windows上，尝试写入系统目录来检查管理员权限
        if (process.platform === 'win32') {
            const testPath = path.join(process.env.WINDIR || 'C:\\Windows', 'temp', 'admin-test.tmp');
            try {
                fs.writeFileSync(testPath, 'test');
                fs.unlinkSync(testPath);
                return true;
            }
            catch {
                return false;
            }
        }
        return true; // 非Windows系统暂时返回true
    }
    catch {
        return false;
    }
}
// 重新以管理员权限启动应用
function restartAsAdmin() {
    if (process.platform === 'win32') {
        const exePath = process.execPath;
        const args = process.argv.slice(1);
        // 使用PowerShell以管理员权限启动
        (0, child_process_1.spawn)('powershell', [
            '-Command',
            `Start-Process -FilePath "${exePath}" -ArgumentList "${args.join(' ')}" -Verb RunAs`,
        ], {
            detached: true,
            stdio: 'ignore',
        });
        electron_1.app.quit();
    }
}
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
electron_1.ipcMain.handle('install-pip', async () => {
    const appRoot = (0, environmentService_1.getAppRoot)();
    return (0, pythonService_1.installPipPackage)(appRoot);
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
// 配置文件操作
electron_1.ipcMain.handle('save-config', async (event, config) => {
    try {
        const appRoot = (0, environmentService_1.getAppRoot)();
        const configDir = path.join(appRoot, 'config');
        const configPath = path.join(configDir, 'frontend_config.json');
        // 确保config目录存在
        if (!fs.existsSync(configDir)) {
            fs.mkdirSync(configDir, { recursive: true });
        }
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
        console.log(`配置已保存到: ${configPath}`);
    }
    catch (error) {
        console.error('保存配置文件失败:', error);
        throw error;
    }
});
electron_1.ipcMain.handle('load-config', async () => {
    try {
        const appRoot = (0, environmentService_1.getAppRoot)();
        const configPath = path.join(appRoot, 'config', 'frontend_config.json');
        if (fs.existsSync(configPath)) {
            const config = fs.readFileSync(configPath, 'utf8');
            console.log(`从文件加载配置: ${configPath}`);
            return JSON.parse(config);
        }
        return null;
    }
    catch (error) {
        console.error('加载配置文件失败:', error);
        return null;
    }
});
electron_1.ipcMain.handle('reset-config', async () => {
    try {
        const appRoot = (0, environmentService_1.getAppRoot)();
        const configPath = path.join(appRoot, 'config', 'frontend_config.json');
        if (fs.existsSync(configPath)) {
            fs.unlinkSync(configPath);
            console.log(`配置文件已删除: ${configPath}`);
        }
    }
    catch (error) {
        console.error('重置配置文件失败:', error);
        throw error;
    }
});
// 日志文件操作
electron_1.ipcMain.handle('save-logs-to-file', async (event, logs) => {
    try {
        const appRoot = (0, environmentService_1.getAppRoot)();
        const logsDir = path.join(appRoot, 'logs');
        // 确保logs目录存在
        if (!fs.existsSync(logsDir)) {
            fs.mkdirSync(logsDir, { recursive: true });
        }
        const logFilePath = path.join(logsDir, 'app.log');
        fs.writeFileSync(logFilePath, logs, 'utf8');
        console.log(`日志已保存到: ${logFilePath}`);
    }
    catch (error) {
        console.error('保存日志文件失败:', error);
        throw error;
    }
});
electron_1.ipcMain.handle('load-logs-from-file', async () => {
    try {
        const appRoot = (0, environmentService_1.getAppRoot)();
        const logFilePath = path.join(appRoot, 'logs', 'app.log');
        if (fs.existsSync(logFilePath)) {
            const logs = fs.readFileSync(logFilePath, 'utf8');
            console.log(`从文件加载日志: ${logFilePath}`);
            return logs;
        }
        return null;
    }
    catch (error) {
        console.error('加载日志文件失败:', error);
        return null;
    }
});
// 管理员权限相关
electron_1.ipcMain.handle('check-admin', () => {
    return isRunningAsAdmin();
});
electron_1.ipcMain.handle('restart-as-admin', () => {
    restartAsAdmin();
});
// 应用生命周期
// 保证应用单例运行
const gotTheLock = electron_1.app.requestSingleInstanceLock();
if (!gotTheLock) {
    electron_1.app.quit();
    process.exit(0);
}
electron_1.app.on('second-instance', () => {
    if (mainWindow) {
        if (mainWindow.isMinimized())
            mainWindow.restore();
        mainWindow.focus();
    }
});
electron_1.app.whenReady().then(() => {
    // 检查管理员权限
    if (!isRunningAsAdmin()) {
        console.log('应用未以管理员权限运行');
        // 在生产环境中，可以选择是否强制要求管理员权限
        // 这里先创建窗口，让用户选择是否重新启动
    }
    createWindow();
});
electron_1.app.on('window-all-closed', () => {
    if (process.platform !== 'darwin')
        electron_1.app.quit();
});
electron_1.app.on('activate', () => {
    if (mainWindow === null)
        createWindow();
});
