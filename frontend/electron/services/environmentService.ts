/** 应用数据根目录定位。 */
import * as path from 'path'
import { app } from 'electron'
import { isDevelopmentEnvironment } from './instanceConfig'

export function getAppRoot(): string {
  if (!app) return process.cwd()
  return isDevelopmentEnvironment()
    ? path.dirname(app.getAppPath())
    : path.dirname(app.getPath('exe'))
}
