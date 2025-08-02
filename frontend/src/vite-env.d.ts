/// <reference types="vite/client" />

declare global {
  interface Window {
    electronAPI?: {
      openDevTools: () => void
    }
  }
}
