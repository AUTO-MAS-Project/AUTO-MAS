import { contextBridge, ipcRenderer } from 'electron'
import type { DesktopMascotMenuAPI, DesktopMascotMenuData } from '../src/types/desktopMascot'

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
