export {}

declare global {
  interface Window {
    electronAPI: {
      openDevTools: () => void
    }
  }
}
