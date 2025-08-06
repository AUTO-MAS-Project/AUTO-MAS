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

const gitDownloadUrl = 'https://alist-automaa.fearr.xyz/d/AUTO_MAA/git.zip'

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
    GIT_HTTP_LOW_SPEED_TIME: '0'
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
        message: '开始下载Git...'
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
        message: '正在解压Git...'
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
        message: 'Git安装完成'
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
        message: `Git下载失败: ${errorMessage}`
      })
    }
    return { success: false, error: errorMessage }
  }
}

// 克隆后端代码
export async function cloneBackend(appRoot: string, repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git'): Promise<{ success: boolean; error?: string }> {
  try {
    const backendPath = path.join(appRoot)
    const backendCheckPath = path.join(appRoot,'app')
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')

    console.log(`开始获取后端代码`)
    console.log(`Git路径: ${gitPath}`)
    console.log(`仓库URL: ${repoUrl}`)
    console.log(`目标路径: ${backendPath}`)

    // 检查Git可执行文件是否存在
    if (!fs.existsSync(gitPath)) {
      throw new Error(`Git可执行文件不存在: ${gitPath}`)
    }

    // 获取Git环境变量
    const gitEnv = getGitEnvironment(appRoot)

    // 先测试Git是否能正常运行
    console.log('测试Git版本...')
    try {
      await new Promise<void>((resolve, reject) => {
        const testProcess = spawn(gitPath, ['--version'], {
          stdio: 'pipe',
          env: gitEnv
        })

        testProcess.stdout?.on('data', (data) => {
          console.log('Git版本信息:', data.toString())
        })

        testProcess.stderr?.on('data', (data) => {
          console.log('Git版本错误:', data.toString())
        })

        testProcess.on('close', (code) => {
          if (code === 0) {
            console.log('Git版本检查成功')
            resolve()
          } else {
            reject(new Error(`Git版本检查失败，退出码: ${code}`))
          }
        })

        testProcess.on('error', (error) => {
          reject(error)
        })
      })
    } catch (error) {
      console.error('Git版本检查失败:', error)
      throw new Error(`Git无法正常运行: ${error}`)
    }

    console.log('Git环境变量:', gitEnv)

    // 检查backend目录是否存在且是否为Git仓库
    if (fs.existsSync(backendCheckPath)) {
      if (isGitRepository(backendPath)) {
        // 如果是Git仓库，执行pull更新
        console.log('检测到Git仓库，执行pull更新...')

        if (mainWindow) {
          mainWindow.webContents.send('download-progress', {
            type: 'backend',
            progress: 0,
            status: 'downloading',
            message: '正在更新后端代码...'
          })
        }

        await new Promise<void>((resolve, reject) => {
          const process = spawn(gitPath, [
            'clone',
            '--progress',
            '--verbose',
            '-b', 'feature/refactor-backend',
            repoUrl,
            backendPath
          ], {
            stdio: 'pipe',
            env: gitEnv,
            cwd: appRoot
          })

          process.stdout?.on('data', (data) => {
            const output = data.toString()
            console.log('Git pull output:', output)
          })

          process.stderr?.on('data', (data) => {
            const errorOutput = data.toString()
            console.log('Git pull stderr:', errorOutput)
          })

          process.on('close', (code) => {
            console.log(`git pull完成，退出码: ${code}`)
            if (code === 0) {
              resolve()
            } else {
              reject(new Error(`代码更新失败，退出码: ${code}`))
            }
          })

          process.on('error', (error) => {
            console.error('git pull进程错误:', error)
            reject(error)
          })
        })

        if (mainWindow) {
          mainWindow.webContents.send('download-progress', {
            type: 'backend',
            progress: 100,
            status: 'completed',
            message: '后端代码更新完成'
          })
        }
      } else {
        // 如果目录存在但不是Git仓库，删除后重新克隆
        console.log('目录存在但不是Git仓库，删除后重新克隆...')
        fs.rmSync(backendPath, { recursive: true, force: true })

        if (mainWindow) {
          mainWindow.webContents.send('download-progress', {
            type: 'backend',
            progress: 0,
            status: 'downloading',
            message: '正在克隆后端代码...'
          })
        }

        await new Promise<void>((resolve, reject) => {
          const process = spawn(gitPath, [
            'clone',
            '--progress',
            '--verbose',
            repoUrl,
            backendPath
          ], {
            stdio: 'pipe',
            env: gitEnv,
            cwd: appRoot
          })

          process.stdout?.on('data', (data) => {
            const output = data.toString()
            console.log('Git clone output:', output)
          })

          process.stderr?.on('data', (data) => {
            const errorOutput = data.toString()
            console.log('Git clone stderr:', errorOutput)
          })

          process.on('close', (code) => {
            console.log(`git clone完成，退出码: ${code}`)
            if (code === 0) {
              resolve()
            } else {
              reject(new Error(`代码克隆失败，退出码: ${code}`))
            }
          })

          process.on('error', (error) => {
            console.error('git clone进程错误:', error)
            reject(error)
          })
        })

        if (mainWindow) {
          mainWindow.webContents.send('download-progress', {
            type: 'backend',
            progress: 100,
            status: 'completed',
            message: '后端代码克隆完成'
          })
        }
      }
    } else {
      // 如果目录不存在，直接克隆
      console.log('目录不存在，开始克隆...')

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: '正在克隆后端代码...'
        })
      }

      await new Promise<void>((resolve, reject) => {
        const process = spawn(gitPath, [
          'clone',
          '--progress',
          '--verbose',
          '-b', 'feature/refactor-backend',
          repoUrl,
          backendPath
        ], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: appRoot
        })

        process.stdout?.on('data', (data) => {
          const output = data.toString()
          console.log('Git clone output:', output)
        })

        process.stderr?.on('data', (data) => {
          const errorOutput = data.toString()
          console.log('Git clone stderr:', errorOutput)
        })

        process.on('close', (code) => {
          console.log(`git clone完成，退出码: ${code}`)
          if (code === 0) {
            resolve()
          } else {
            reject(new Error(`代码克隆失败，退出码: ${code}`))
          }
        })

        process.on('error', (error) => {
          console.error('git clone进程错误:', error)
          reject(error)
        })
      })

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 100,
          status: 'completed',
          message: '后端代码克隆完成'
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
        message: `后端代码获取失败: ${errorMessage}`
      })
    }
    return { success: false, error: errorMessage }
  }
}