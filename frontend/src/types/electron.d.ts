export {}

declare global {
  interface Window {
    electronAPI: {
      openDevTools: () => void,
      selectFolder: () => Promise<string | null>
      selectFile: (filters?: Array<{ name: string; extensions: string[] }>) => Promise<string | null>
    }
  }
}
