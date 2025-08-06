"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
window.addEventListener('DOMContentLoaded', () => {
    console.log('Preload loaded');
});
// 暴露安全的 API 给渲染进程
electron_1.contextBridge.exposeInMainWorld('electronAPI', {
    openDevTools: () => electron_1.ipcRenderer.invoke('open-dev-tools'),
    selectFolder: () => electron_1.ipcRenderer.invoke('select-folder'),
    selectFile: (filters) => electron_1.ipcRenderer.invoke('select-file', filters),
    // 初始化相关API
    checkEnvironment: () => electron_1.ipcRenderer.invoke('check-environment'),
    downloadPython: (mirror) => electron_1.ipcRenderer.invoke('download-python', mirror),
    downloadGit: () => electron_1.ipcRenderer.invoke('download-git'),
    installDependencies: (mirror) => electron_1.ipcRenderer.invoke('install-dependencies', mirror),
    cloneBackend: (repoUrl) => electron_1.ipcRenderer.invoke('clone-backend', repoUrl),
    updateBackend: (repoUrl) => electron_1.ipcRenderer.invoke('update-backend', repoUrl),
    startBackend: () => electron_1.ipcRenderer.invoke('start-backend'),
    // 日志文件操作
    saveLogsToFile: (logs) => electron_1.ipcRenderer.invoke('save-logs-to-file', logs),
    loadLogsFromFile: () => electron_1.ipcRenderer.invoke('load-logs-from-file'),
    // 监听下载进度
    onDownloadProgress: (callback) => {
        electron_1.ipcRenderer.on('download-progress', (_, progress) => callback(progress));
    },
    removeDownloadProgressListener: () => {
        electron_1.ipcRenderer.removeAllListeners('download-progress');
    }
});
