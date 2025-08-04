/// <reference types="vite/client" />

declare global {
  interface Window {
    electronAPI?: {
      openDevTools: () => Promise<void>
      selectFolder: () => Promise<string | null>
      selectFile: (filters?: Array<{ name: string; extensions: string[] }>) => Promise<string | null>
    }
  }
}
