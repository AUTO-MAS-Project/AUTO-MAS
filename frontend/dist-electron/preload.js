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
    selectFile: (filters) => electron_1.ipcRenderer.invoke('select-file', filters)
});
