import * as path from 'path'
import * as fs from 'fs'
import { spawn } from 'child_process'
import { BrowserWindow } from 'electron'
import AdmZip from 'adm-zip'
import { downloadFile } from './downloadService'

let mainWindow: BrowserWindow | null = null

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
}

const gitDownloadUrl = 'http://221.236.27.82:10197/d/AUTO_MAA/git.zip'

// 递归复制目录，包括文件和隐藏文件
function copyDirSync(src: string, dest: string) {
  if (!fs.existsSync(dest)) {
    fs.mkdirSync(dest, { recursive: true })
  }
  const entries = fs.readdirSync(src, { withFileTypes: true })
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name)
    const destPath = path.join(dest, entry.name)
    if (entry.isDirectory()) {
      copyDirSync(srcPath, destPath)
    } else {
      // 直接覆盖写，不需要先删除
      fs.copyFileSync(srcPath, destPath)
    }
  }
}

// 获取Git环境变量配置
function getGitEnvironment(appRoot: string) {
  const gitDir = path.join(appRoot, 'environment', 'git')
  const binPath = path.join(gitDir, 'bin')
  const mingw64BinPath = path.join(gitDir, 'mingw64', 'bin')
  const gitCorePath = path.join(gitDir, 'mingw64', 'libexec', 'git-core')

  return {
    ...process.env,
    // 修复remote-https问题的关键：确保所有Git相关路径都在PATH中
    PATH: `${binPath};${mingw64BinPath};${gitCorePath};${process.env.PATH}`,
    GIT_EXEC_PATH: gitCorePath,
    GIT_TEMPLATE_DIR: path.join(gitDir, 'mingw64', 'share', 'git-core', 'templates'),
    HOME: process.env.USERPROFILE || process.env.HOME,
    // // SSL证书路径
    // GIT_SSL_CAINFO: path.join(gitDir, 'mingw64', 'ssl', 'certs', 'ca-bundle.crt'),
    // 禁用系统Git配置
    GIT_CONFIG_NOSYSTEM: '1',
    // 禁用交互式认证
    GIT_TERMINAL_PROMPT: '0',
    GIT_ASKPASS: '',
    // // 修复remote-https问题的关键环境变量
    // CURL_CA_BUNDLE: path.join(gitDir, 'mingw64', 'ssl', 'certs', 'ca-bundle.crt'),
    // 确保Git能找到所有必要的程序
    GIT_HTTP_LOW_SPEED_LIMIT: '0',
    GIT_HTTP_LOW_SPEED_TIME: '0',
  }
}

// 检查是否为Git仓库
function isGitRepository(dirPath: string): boolean {
  const gitDir = path.join(dirPath, '.git')
  return fs.existsSync(gitDir)
}

// 下载Git
export async function downloadGit(appRoot: string): Promise<{ success: boolean; error?: string }> {
  try {
    const environmentPath = path.join(appRoot, 'environment')
    const gitPath = path.join(environmentPath, 'git')

    if (!fs.existsSync(environmentPath)) {
      fs.mkdirSync(environmentPath, { recursive: true })
    }

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'git',
        progress: 0,
        status: 'downloading',
        message: '开始下载Git...',
      })
    }

    // 使用自定义Git压缩包
    const zipPath = path.join(environmentPath, 'git.zip')
    await downloadFile(gitDownloadUrl, zipPath)

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'git',
        progress: 100,
        status: 'extracting',
        message: '正在解压Git...',
      })
    }

    // 解压Git到临时目录，然后移动到正确位置
    console.log(`开始解压Git到: ${gitPath}`)

    // 创建临时解压目录
    const tempExtractPath = path.join(environmentPath, 'git_temp')
    if (!fs.existsSync(tempExtractPath)) {
      fs.mkdirSync(tempExtractPath, { recursive: true })
      console.log(`创建临时解压目录: ${tempExtractPath}`)
    }

    // 解压到临时目录
    const zip = new AdmZip(zipPath)
    zip.extractAllTo(tempExtractPath, true)
    console.log(`Git解压到临时目录: ${tempExtractPath}`)

    // 检查解压后的目录结构
    const tempContents = fs.readdirSync(tempExtractPath)
    console.log(`临时目录内容:`, tempContents)

    // 如果解压后有git子目录，则从git子目录移动内容
    let sourceDir = tempExtractPath
    if (tempContents.length === 1 && tempContents[0] === 'git') {
      sourceDir = path.join(tempExtractPath, 'git')
      console.log(`检测到git子目录，使用源目录: ${sourceDir}`)
    }

    // 确保目标Git目录存在
    if (!fs.existsSync(gitPath)) {
      fs.mkdirSync(gitPath, { recursive: true })
      console.log(`创建Git目录: ${gitPath}`)
    }

    // 移动文件到最终目录
    const sourceContents = fs.readdirSync(sourceDir)
    for (const item of sourceContents) {
      const sourcePath = path.join(sourceDir, item)
      const targetPath = path.join(gitPath, item)

      // 如果目标已存在，先删除
      if (fs.existsSync(targetPath)) {
        if (fs.statSync(targetPath).isDirectory()) {
          fs.rmSync(targetPath, { recursive: true, force: true })
        } else {
          fs.unlinkSync(targetPath)
        }
      }

      // 移动文件或目录
      fs.renameSync(sourcePath, targetPath)
      console.log(`移动: ${sourcePath} -> ${targetPath}`)
    }

    // 清理临时目录
    fs.rmSync(tempExtractPath, { recursive: true, force: true })
    console.log(`清理临时目录: ${tempExtractPath}`)

    console.log(`Git解压完成到: ${gitPath}`)

    // 删除zip文件
    fs.unlinkSync(zipPath)
    console.log(`删除临时文件: ${zipPath}`)

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'git',
        progress: 100,
        status: 'completed',
        message: 'Git安装完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'git',
        progress: 0,
        status: 'error',
        message: `Git下载失败: ${errorMessage}`,
      })
    }
    return { success: false, error: errorMessage }
  }
}

// 克隆后端代码（替换原有核心逻辑）
export async function cloneBackend(
  appRoot: string,
  repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git'
): Promise<{
  success: boolean
  error?: string
}> {
  try {
    const backendPath = appRoot
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
    if (!fs.existsSync(gitPath)) throw new Error(`Git可执行文件不存在: ${gitPath}`)
    const gitEnv = getGitEnvironment(appRoot)

    // 检查 git 是否可用
    await new Promise<void>((resolve, reject) => {
      const proc = spawn(gitPath, ['--version'], { env: gitEnv })
      proc.on('close', code => (code === 0 ? resolve() : reject(new Error('git 无法正常运行'))))
      proc.on('error', reject)
    })

    // ==== 下面是关键逻辑 ====
    if (isGitRepository(backendPath)) {
      // 已是 git 仓库，直接 pull
      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: '正在更新后端代码...',
        })
      }
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['pull'], { stdio: 'pipe', env: gitEnv, cwd: backendPath })
        proc.stdout?.on('data', d => console.log('git pull:', d.toString()))
        proc.stderr?.on('data', d => console.log('git pull err:', d.toString()))
        proc.on('close', code =>
          code === 0 ? resolve() : reject(new Error(`git pull失败，退出码: ${code}`))
        )
        proc.on('error', reject)
      })
      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 100,
          status: 'completed',
          message: '后端代码更新完成',
        })
      }
    } else {
      // 不是 git 仓库，clone 到 tmp，再拷贝出来
      const tmpDir = path.join(appRoot, 'git_tmp')
      if (fs.existsSync(tmpDir)) fs.rmSync(tmpDir, { recursive: true, force: true })
      fs.mkdirSync(tmpDir, { recursive: true })

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: '正在克隆后端代码...',
        })
      }
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(
          gitPath,
          [
            'clone',
            '--progress',
            '--verbose',
            '--single-branch',
            '--depth',
            '1',
            '--branch',
            'feature/refactor',
            repoUrl,
            tmpDir,
          ],
          {
            stdio: 'pipe',
            env: gitEnv,
            cwd: appRoot,
          }
        )
        proc.stdout?.on('data', d => console.log('git clone:', d.toString()))
        proc.stderr?.on('data', d => console.log('git clone err:', d.toString()))
        proc.on('close', code =>
          code === 0 ? resolve() : reject(new Error(`git clone失败，退出码: ${code}`))
        )
        proc.on('error', reject)
      })

      // 复制所有文件到 backendPath（appRoot），包含 .git
      const tmpFiles = fs.readdirSync(tmpDir)
      for (const file of tmpFiles) {
        const src = path.join(tmpDir, file)
        const dst = path.join(backendPath, file)
        if (fs.existsSync(dst)) {
          if (fs.statSync(dst).isDirectory()) fs.rmSync(dst, { recursive: true, force: true })
          else fs.unlinkSync(dst)
        }
        if (fs.statSync(src).isDirectory()) copyDirSync(src, dst)
        else fs.copyFileSync(src, dst)
      }
      fs.rmSync(tmpDir, { recursive: true, force: true })

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 100,
          status: 'completed',
          message: '后端代码克隆完成',
        })
      }
    }
    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    console.error('获取后端代码失败:', errorMessage)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'backend',
        progress: 0,
        status: 'error',
        message: `后端代码获取失败: ${errorMessage}`,
      })
    }
    return { success: false, error: errorMessage }
  }
}
