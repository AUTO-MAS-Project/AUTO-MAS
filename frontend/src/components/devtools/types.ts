export interface RouteVisit {
  fullPath: string
  time: string
}

export interface StorageEntry {
  key: string
  value: string
  type: 'json' | 'text'
  bytes: number
}
