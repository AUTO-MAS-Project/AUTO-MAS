export interface UpgradeBackupDirectory {
  directory: string | null
  resolvedDirectory: string
  defaultDirectory: string
  cleanupPending?: boolean
}

export interface UpgradeBackupSelection {
  id: string
  current: string
  target: string
}
