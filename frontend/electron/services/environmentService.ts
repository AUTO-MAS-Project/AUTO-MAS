import * as path from 'path'
import * as fs from 'fs'
import { app } from 'electron'

// 获取应用根目录
export function getAppRoot(): string {
  return process.env.NODE_ENV === 'development' ? process.cwd() : path.dirname(app.getPath('exe'))
}

// 检查环境
export function checkEnvironment(appRoot: string) {
  const environmentPath = path.join(appRoot, 'environment')
  const pythonPath = path.join(environmentPath, 'python')
  const gitPath = path.join(environmentPath, 'git')
  const backendPath = path.join(appRoot, 'backend')
  const requirementsPath = path.join(backendPath, 'requirements.txt')

  const pythonExists = fs.existsSync(pythonPath)
  const gitExists = fs.existsSync(gitPath)
  const backendExists = fs.existsSync(backendPath)

  // 检查依赖是否已安装（简单检查是否存在site-packages目录）
  const sitePackagesPath = path.join(pythonPath, 'Lib', 'site-packages')
  const dependenciesInstalled =
    fs.existsSync(sitePackagesPath) && fs.readdirSync(sitePackagesPath).length > 10

  return {
    pythonExists,
    gitExists,
    backendExists,
    dependenciesInstalled,
    isInitialized: pythonExists && gitExists && backendExists && dependenciesInstalled,
  }
}
