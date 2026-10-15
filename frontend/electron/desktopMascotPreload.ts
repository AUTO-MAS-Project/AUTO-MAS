import { contextBridge, ipcRenderer } from 'electron'
import type {
  DesktopMascotAPI,
  DesktopMascotData,
  DesktopMascotUpdate,
} from '../src/types/desktopMascot'

// 桌宠只读取已经校验的图片，不加载主窗口的后端、配置和文件操作入口。
const api: DesktopMascotAPI = {
  getData: () => ipcRenderer.invoke('desktop-mascot:get'),
  pointer: action => ipcRenderer.send('desktop-mascot:pointer', action),
  imageDecoded: (imageUrl, pngDataUrl) =>
    ipcRenderer.send('desktop-mascot:image-decoded', imageUrl, pngDataUrl),
  onLookChanged: callback => {
    const listener = (_event: Electron.IpcRendererEvent, frame: number | null) => callback(frame)
    ipcRenderer.on('desktop-mascot:look', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:look', listener)
  },
  onChanged: callback => {
    const listener = (_event: Electron.IpcRendererEvent, data: DesktopMascotData) => callback(data)
    ipcRenderer.on('desktop-mascot:changed', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:changed', listener)
  },
  onUpdated: callback => {
    const listener = (_event: Electron.IpcRendererEvent, update: DesktopMascotUpdate) =>
      callback(update)
    ipcRenderer.on('desktop-mascot:updated', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:updated', listener)
  },
}

contextBridge.exposeInMainWorld('desktopMascotAPI', api)
