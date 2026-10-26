import { contextBridge, ipcRenderer } from 'electron'

import type { DesktopMascotMenuAPI, DesktopMascotMenuData } from '../src/types/desktopMascot'

// 环境在页面执行前可用；沙箱 preload 只读取主进程传入的启动参数。
contextBridge.exposeInMainWorld(
  'appEnvironment',
  process.argv.includes('--auto-mas-environment=production') ? 'production' : 'development'
)

const api: DesktopMascotMenuAPI = {
  getData: () => ipcRenderer.invoke('desktop-mascot-menu:get'),
  getViewport: () => ipcRenderer.invoke('desktop-mascot-menu:viewport'),
  resize: size => ipcRenderer.send('desktop-mascot-menu:resize', size),
  onChanged: callback => {
    const listener = (_event: Electron.IpcRendererEvent, data: DesktopMascotMenuData) =>
      callback(data)
    ipcRenderer.on('desktop-mascot-menu:changed', listener)
    return () => ipcRenderer.removeListener('desktop-mascot-menu:changed', listener)
  },
  execute: action => ipcRenderer.invoke('desktop-mascot-menu:execute', action),
  close: () => ipcRenderer.send('desktop-mascot-menu:close'),
}

contextBridge.exposeInMainWorld('desktopMascotMenuAPI', api)
