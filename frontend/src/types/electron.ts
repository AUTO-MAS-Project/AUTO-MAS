// Electron API 类型定义
export interface ElectronAPI {
  openDevTools: () => Promise<void>
  selectFolder: () => Promise<string | null>
  selectFile: (filters?: { name: string; extensions: string[] }[]) => Promise<string | null>
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}

export {}