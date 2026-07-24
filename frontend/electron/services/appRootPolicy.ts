import * as path from 'path'

export interface AppRootProvider {
  isPackaged?: boolean
  getPath(name: 'exe'): string
}

/** Packaged applications must derive their root from the executable, never inherited dev flags. */
export function resolveAppRoot(
  electronApp: AppRootProvider | undefined,
  environment: NodeJS.ProcessEnv = process.env,
  currentDirectory: string = process.cwd()
): string {
  if (!electronApp) return currentDirectory
  if (electronApp.isPackaged) return path.dirname(electronApp.getPath('exe'))
  if (environment.NODE_ENV === 'development') return currentDirectory
  return path.dirname(electronApp.getPath('exe'))
}
