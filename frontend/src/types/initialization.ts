export interface InitializationStatus {
  pythonExists: boolean
  gitExists: boolean
  backendExists: boolean
  dependenciesInstalled: boolean
  isInitialized: boolean
}

export interface DownloadProgress {
  type: 'python' | 'git' | 'backend' | 'dependencies' | 'service'
  progress: number
  status: 'downloading' | 'extracting' | 'installing' | 'completed' | 'error'
  message: string
}

export interface MirrorSource {
  key: string
  name: string
  url: string
  speed: number | null
}
