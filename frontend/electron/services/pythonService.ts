import * as path from 'path'
import * as fs from 'fs'
import { spawn } from 'child_process'
import { BrowserWindow } from 'electron'
import AdmZip from 'adm-zip'
import { downloadFile, downloadFileMultiThread } from './downloadService'
import { ChildProcessWithoutNullStreams } from 'node:child_process'
import { log, stripAnsiColors } from './logService'
import * as crypto from 'crypto'

let mainWindow: BrowserWindow | null = null

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
}

// 通用的智能下载函数，带有自动回退机制
async function downloadWithFallback(
  url: string,
  outputPath: string,
  threadCount: number = 6,
  progressInfo?: { type?: string; step?: number; message?: string }
): Promise<void> {
  // 对于小文件（< 5MB），直接使用单线程下载
  const minSizeForMultiThread = 5 * 1024 * 1024 // 5MB

  try {
    console.log(`开始智能下载: ${url}`)

    // 先尝试获取文件大小
    let useMultiThread = true
    try {
      const https = require('https')
      const http = require('http')
      const client = url.startsWith('https') ? https : http

      const fileSize = await new Promise<number>((resolve, reject) => {
        const req = client.request(url, { method: 'HEAD' }, (response: any) => {
          const size = parseInt(response.headers['content-length'] || '0', 10)
          resolve(size)
        })
        req.on('error', () => resolve(0)) // 如果获取失败，默认使用多线程
        req.setTimeout(5000, () => {
          req.destroy()
          resolve(0)
        })
        req.end()
      })

      if (fileSize > 0 && fileSize < minSizeForMultiThread) {
        console.log(`文件大小 ${(fileSize / 1024 / 1024).toFixed(2)} MB < 5MB，使用单线程下载`)
        useMultiThread = false
      } else if (fileSize > 0) {
        // 根据文件大小智能调整线程数
        const fileSizeMB = fileSize / 1024 / 1024
        let optimalThreads = threadCount

        if (fileSizeMB < 20) {
          optimalThreads = Math.min(4, threadCount) // 小于20MB使用最多4线程
        } else if (fileSizeMB < 100) {
          optimalThreads = Math.min(6, threadCount) // 小于100MB使用最多6线程
        } else {
          optimalThreads = threadCount // 大文件使用指定线程数
        }

        threadCount = optimalThreads
        console.log(`文件大小 ${fileSizeMB.toFixed(2)} MB，使用 ${threadCount} 线程下载`)
      }
    } catch (error) {
      console.log('无法获取文件大小，默认使用多线程下载')
    }

    if (useMultiThread) {
      await downloadFileMultiThread(url, outputPath, threadCount)
      console.log(`多线程下载成功: ${outputPath}`)
    } else {
      await downloadFile(url, outputPath)
      console.log(`单线程下载成功: ${outputPath}`)
    }
  } catch (multiThreadError) {
    console.warn(`多线程下载失败，回退到单线程下载:`, multiThreadError)

    if (mainWindow && progressInfo) {
      mainWindow.webContents.send('download-progress', {
        type: progressInfo.type,
        step: progressInfo.step,
        progress: 10,
        status: 'downloading',
        message: progressInfo.message || '回退到单线程下载...',
      })
    }

    await downloadFile(url, outputPath)
    console.log(`单线程下载成功: ${outputPath}`)
  }
}

// Python镜像源URL映射
const pythonMirrorUrls = {
  official: 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip',
  tsinghua: 'https://mirrors.tuna.tsinghua.edu.cn/python/3.12.0/python-3.12.0-embed-amd64.zip',
  ustc: 'https://mirrors.ustc.edu.cn/python/3.12.0/python-3.12.0-embed-amd64.zip',
  huawei:
    'https://mirrors.huaweicloud.com/repository/toolkit/python/3.12.0/python-3.12.0-embed-amd64.zip',
  aliyun: 'https://mirrors.aliyun.com/python-release/windows/python-3.12.0-embed-amd64.zip',
}

// 检查pip是否已安装
function isPipInstalled(pythonPath: string): boolean {
  const scriptsPath = path.join(pythonPath, 'Scripts')
  const pipExePath = path.join(scriptsPath, 'pip.exe')
  const pip3ExePath = path.join(scriptsPath, 'pip3.exe')

  console.log(`检查pip安装状态:`)
  console.log(`Scripts目录: ${scriptsPath}`)
  console.log(`pip.exe路径: ${pipExePath}`)
  console.log(`pip3.exe路径: ${pip3ExePath}`)

  const scriptsExists = fs.existsSync(scriptsPath)
  const pipExists = fs.existsSync(pipExePath)
  const pip3Exists = fs.existsSync(pip3ExePath)

  console.log(`Scripts目录存在: ${scriptsExists}`)
  console.log(`pip.exe存在: ${pipExists}`)
  console.log(`pip3.exe存在: ${pip3Exists}`)

  return scriptsExists && (pipExists || pip3Exists)
}

// 安装pip
async function installPip(pythonPath: string, appRoot: string): Promise<void> {
  console.log('开始检查pip安装状态...')

  const pythonExe = path.join(pythonPath, 'python.exe')

  // 检查Python可执行文件是否存在
  if (!fs.existsSync(pythonExe)) {
    throw new Error(`Python可执行文件不存在: ${pythonExe}`)
  }

  // 检查pip是否已安装
  if (isPipInstalled(pythonPath)) {
    console.log('pip已安装，跳过安装过程')
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'pip',
        progress: 100,
        status: 'completed',
        message: 'pip 已安装完成',
      })
    }
    return
  }

  console.log('pip未安装，开始安装...')

  const getPipPath = path.join(pythonPath, 'get-pip.py')
  const getPipUrl = 'https://download.auto-mas.top/d/AUTO-MAS/get-pip.py'

  console.log(`Python可执行文件路径: ${pythonExe}`)
  console.log(`get-pip.py下载URL: ${getPipUrl}`)
  console.log(`get-pip.py保存路径: ${getPipPath}`)

  // 下载get-pip.py
  console.log('开始下载get-pip.py...')
  try {
    // 智能下载get-pip.py，自动选择最佳下载方式
    await downloadWithFallback(getPipUrl, getPipPath, 4, {
      type: 'pip',
      message: '回退到单线程下载get-pip.py...'
    })
    console.log('get-pip.py下载完成')

    // 检查下载的文件大小
    const stats = fs.statSync(getPipPath)
    console.log(`get-pip.py文件大小: ${stats.size} bytes`)

    if (stats.size < 10000) {
      // 如果文件小于10KB，可能是无效文件
      throw new Error(`get-pip.py文件大小异常: ${stats.size} bytes，可能下载失败`)
    }
  } catch (error) {
    console.error('下载get-pip.py失败:', error)
    throw new Error(`下载get-pip.py失败: ${error}`)
  }

  // 执行pip安装
  await new Promise<void>((resolve, reject) => {
    console.log('执行pip安装命令...')

    const process = spawn(pythonExe, [getPipPath], {
      cwd: pythonPath,
      stdio: 'pipe',
    })

    process.stdout?.on('data', data => {
      const output = stripAnsiColors(data.toString())
      log.info('pip安装输出:', output)
    })

    process.stderr?.on('data', data => {
      const errorOutput = stripAnsiColors(data.toString())
      log.warn('pip安装错误输出:', errorOutput)
    })

    process.on('close', code => {
      console.log(`pip安装完成，退出码: ${code}`)
      if (code === 0) {
        console.log('pip安装成功')
        resolve()
      } else {
        reject(new Error(`pip安装失败，退出码: ${code}`))
      }
    })

    process.on('error', error => {
      console.error('pip安装进程错误:', error)
      reject(error)
    })
  })

  // 验证pip是否安装成功
  console.log('验证pip安装...')
  await new Promise<void>((resolve, reject) => {
    const verifyProcess = spawn(pythonExe, ['-m', 'pip', '--version'], {
      cwd: pythonPath,
      stdio: 'pipe',
    })

    verifyProcess.stdout?.on('data', data => {
      const output = stripAnsiColors(data.toString())
      log.info('pip版本信息:', output)
    })

    verifyProcess.stderr?.on('data', data => {
      const errorOutput = stripAnsiColors(data.toString())
      log.warn('pip版本检查错误:', errorOutput)
    })

    verifyProcess.on('close', code => {
      if (code === 0) {
        console.log('pip验证成功')
        resolve()
      } else {
        reject(new Error(`pip验证失败，退出码: ${code}`))
      }
    })

    verifyProcess.on('error', error => {
      console.error('pip验证进程错误:', error)
      reject(error)
    })
  })

  // 清理临时文件
  console.log('清理临时文件...')
  try {
    if (fs.existsSync(getPipPath)) {
      fs.unlinkSync(getPipPath)
      console.log('get-pip.py临时文件已删除')
    }
  } catch (error) {
    console.warn('清理get-pip.py文件时出错:', error)
  }

  console.log('pip安装和验证完成')
}

// 快速安装：下载预打包环境
export async function downloadQuickEnvironment(appRoot: string): Promise<{ success: boolean; error?: string }> {
  try {
    const environmentUrl = 'https://download.auto-mas.top/d/AUTO-MAS/environment.zip'
    const downloadPath = path.join(appRoot, 'temp', 'environment.zip')

    // 确保临时目录存在
    const tempDir = path.dirname(downloadPath)
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true })
    }

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 0,
        progress: 10,
        status: 'downloading',
        message: '开始多线程下载环境包...',
      })
    }

    // 智能下载环境包，自动选择最佳线程数
    await downloadWithFallback(environmentUrl, downloadPath, 8, {
      step: 0,
      message: '回退到单线程下载环境包...'
    })

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 0,
        progress: 20,
        status: 'completed',
        message: '环境包下载完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMsg = `环境包下载失败: ${error instanceof Error ? error.message : String(error)}`
    console.error(errorMsg)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 0,
        progress: 0,
        status: 'error',
        message: errorMsg,
      })
    }
    return { success: false, error: errorMsg }
  }
}

// 快速安装：解压预打包环境
export async function extractQuickEnvironment(appRoot: string): Promise<{ success: boolean; error?: string }> {
  try {
    const zipPath = path.join(appRoot, 'temp', 'environment.zip')
    const extractPath = appRoot

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 1,
        progress: 30,
        status: 'extracting',
        message: '开始解压环境包...',
      })
    }

    if (!fs.existsSync(zipPath)) {
      throw new Error('环境包文件不存在')
    }

    // 使用AdmZip解压
    const zip = new AdmZip(zipPath)
    zip.extractAllTo(extractPath, true)

    // 删除临时文件
    fs.unlinkSync(zipPath)

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 1,
        progress: 40,
        status: 'completed',
        message: '环境包解压完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMsg = `环境包解压失败: ${error instanceof Error ? error.message : String(error)}`
    console.error(errorMsg)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 1,
        progress: 0,
        status: 'error',
        message: errorMsg,
      })
    }
    return { success: false, error: errorMsg }
  }
}

// 下载Python
export async function downloadPython(
  appRoot: string,
  mirror = 'ustc'
): Promise<{ success: boolean; error?: string }> {
  try {
    const environmentPath = path.join(appRoot, 'environment')
    const pythonPath = path.join(environmentPath, 'python')

    // 确保environment目录存在
    if (!fs.existsSync(environmentPath)) {
      fs.mkdirSync(environmentPath, { recursive: true })
    }

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'python',
        progress: 0,
        status: 'downloading',
        message: '开始多线程下载Python...',
      })
    }

    // 根据选择的镜像源获取下载链接
    const pythonUrl =
      pythonMirrorUrls[mirror as keyof typeof pythonMirrorUrls] || pythonMirrorUrls.ustc
    const zipPath = path.join(environmentPath, 'python.zip')

    // 智能下载Python，自动选择最佳线程数
    await downloadWithFallback(pythonUrl, zipPath, 6, {
      type: 'python',
      message: '回退到单线程下载Python...'
    })

    // 检查下载的Python文件大小
    const stats = fs.statSync(zipPath)
    console.log(
      `Python压缩包大小: ${stats.size} bytes (${(stats.size / 1024 / 1024).toFixed(2)} MB)`
    )

    // Python 3.12.0嵌入式版本应该大约30MB，如果小于5MB可能是无效文件
    if (stats.size < 5 * 1024 * 1024) {
      // 5MB
      fs.unlinkSync(zipPath) // 删除无效文件
      throw new Error(
        `Python下载文件大小异常: ${stats.size} bytes (${(stats.size / 1024).toFixed(2)} KB)。可能是对应镜像站不可用。请选择任意一个其他镜像源进行下载！`
      )
    }

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'python',
        progress: 100,
        status: 'extracting',
        message: '正在解压Python...',
      })
    }

    // 解压Python到指定目录
    console.log(`开始解压Python到: ${pythonPath}`)

    // 确保Python目录存在
    if (!fs.existsSync(pythonPath)) {
      fs.mkdirSync(pythonPath, { recursive: true })
      console.log(`创建Python目录: ${pythonPath}`)
    }

    const zip = new AdmZip(zipPath)
    zip.extractAllTo(pythonPath, true)
    console.log(`Python解压完成到: ${pythonPath}`)

    // 删除zip文件
    fs.unlinkSync(zipPath)
    console.log(`删除临时文件: ${zipPath}`)

    // 启用 site-packages 支持
    const pthFile = path.join(pythonPath, 'python312._pth')
    if (fs.existsSync(pthFile)) {
      let content = fs.readFileSync(pthFile, 'utf-8')
      content = content.replace(/^#import site/m, 'import site')
      fs.writeFileSync(pthFile, content, 'utf-8')
      console.log('已启用 site-packages 支持')
    }

    // 安装pip
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'python',
        progress: 80,
        status: 'installing',
        message: '正在安装pip...',
      })
    }

    await installPip(pythonPath, appRoot)

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'python',
        progress: 100,
        status: 'completed',
        message: 'Python 和 pip 安装完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'python',
        progress: 0,
        status: 'error',
        message: `Python下载失败: ${errorMessage}`,
      })
    }
    return { success: false, error: errorMessage }
  }
}

// pip镜像源URL映射
const pipMirrorUrls = {
  official: 'https://pypi.org/simple/',
  tsinghua: 'https://pypi.tuna.tsinghua.edu.cn/simple/',
  ustc: 'https://pypi.mirrors.ustc.edu.cn/simple/',
  aliyun: 'https://mirrors.aliyun.com/pypi/simple/',
  douban: 'https://pypi.douban.com/simple/',
}

// 依赖校验相关函数
function getRequirementsHash(requirementsPath: string): string {
  if (!fs.existsSync(requirementsPath)) {
    throw new Error('requirements.txt文件不存在')
  }

  const content = fs.readFileSync(requirementsPath, 'utf-8')
  return crypto.createHash('sha256').update(content.trim()).digest('hex')
}

function getLastInstallHash(appRoot: string): string | null {
  const hashFilePath = path.join(appRoot, 'environment', '.requirements_hash')
  if (!fs.existsSync(hashFilePath)) {
    return null
  }

  try {
    return fs.readFileSync(hashFilePath, 'utf-8').trim()
  } catch (error) {
    console.warn('读取依赖哈希文件失败:', error)
    return null
  }
}

function saveInstallHash(appRoot: string, hash: string): void {
  const environmentPath = path.join(appRoot, 'environment')
  const hashFilePath = path.join(environmentPath, '.requirements_hash')

  // 确保environment目录存在
  if (!fs.existsSync(environmentPath)) {
    fs.mkdirSync(environmentPath, { recursive: true })
  }

  try {
    fs.writeFileSync(hashFilePath, hash, 'utf-8')
    console.log('依赖哈希已保存:', hash)
  } catch (error) {
    console.warn('保存依赖哈希文件失败:', error)
  }
}

function checkRequirementsChanged(appRoot: string): { changed: boolean; currentHash: string; lastHash: string | null } {
  const requirementsPath = path.join(appRoot, 'requirements.txt')
  const currentHash = getRequirementsHash(requirementsPath)
  const lastHash = getLastInstallHash(appRoot)

  const changed = lastHash === null || currentHash !== lastHash

  console.log('依赖校验结果:', {
    changed,
    currentHash: currentHash.substring(0, 8) + '...',
    lastHash: lastHash ? lastHash.substring(0, 8) + '...' : 'null'
  })

  return { changed, currentHash, lastHash }
}

// 安装Python依赖
export async function installDependencies(
  appRoot: string,
  mirror = 'tsinghua',
  forceInstall = false
): Promise<{
  success: boolean
  error?: string
  skipped?: boolean
}> {
  try {
    const pythonPath = path.join(appRoot, 'environment', 'python', 'python.exe')
    const backendPath = path.join(appRoot)
    const requirementsPath = path.join(appRoot, 'requirements.txt')

    // 检查文件是否存在
    if (!fs.existsSync(pythonPath)) {
      throw new Error('Python可执行文件不存在')
    }
    if (!fs.existsSync(requirementsPath)) {
      throw new Error('requirements.txt文件不存在')
    }

    // 检查依赖是否发生更改
    const { changed, currentHash } = checkRequirementsChanged(appRoot)

    if (!forceInstall && !changed) {
      console.log('依赖包已是最新版本，跳过安装过程')
      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          step: 5,
          progress: 100,
          status: 'completed',
          message: '依赖包安装完成',
        })
      }
      return { success: true, skipped: true }
    }

    console.log(forceInstall ? '强制重新安装Python依赖包' : '检测到依赖包更新，开始安装新版本')

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 5,
        progress: 91,
        status: 'downloading',
        message: '正在安装Python依赖包...',
      })
    }

    // 获取pip镜像源URL
    const pipMirrorUrl =
      pipMirrorUrls[mirror as keyof typeof pipMirrorUrls] || pipMirrorUrls.tsinghua

    console.log(`开始安装Python依赖`)
    console.log(`Python可执行文件: ${pythonPath}`)
    console.log(`requirements.txt路径: ${requirementsPath}`)
    console.log(`pip镜像源: ${pipMirrorUrl}`)

    // 检查 Python 是否能运行 pip 命令
    console.log('检查 Python 是否支持 pip 模块...')
    await new Promise<void>((resolve, reject) => {
      const checkProcess = spawn(pythonPath, ['-m', 'pip', '--version'], {
        cwd: backendPath,
        stdio: 'pipe',
      })

      checkProcess.stdout?.on('data', data => {
        const output = stripAnsiColors(data.toString())
        log.info('pip版本检查输出:', output)
      })

      checkProcess.stderr?.on('data', data => {
        const errorOutput = stripAnsiColors(data.toString())
        log.warn('pip版本检查错误:', errorOutput)
      })

      checkProcess.on('close', code => {
        if (code === 0) {
          console.log('pip模块可用，继续安装依赖')
          resolve()
        } else {
          reject(new Error(`Python无法运行pip模块，退出码: ${code}。请确保pip已正确安装。`))
        }
      })

      checkProcess.on('error', error => {
        console.error('pip检查进程错误:', error)
        reject(new Error(`检查pip可用性时出错: ${error.message}`))
      })
    })

    // 安装依赖 - 使用 python -m pip 方法
    await new Promise<void>((resolve, reject) => {
      const process = spawn(
        pythonPath,
        [
          '-m',
          'pip',
          'install',
          '-r',
          requirementsPath,
          '-i',
          pipMirrorUrl,
          '--trusted-host',
          new URL(pipMirrorUrl).hostname,
        ],
        {
          cwd: backendPath,
          stdio: 'pipe',
        }
      )

      process.stdout?.on('data', data => {
        const output = stripAnsiColors(data.toString())
        log.info('Pip output:', output)

        // 解析pip输出，提供更详细的安装进度信息
        if (output.includes('Collecting')) {
          const packageMatch = output.match(/Collecting\s+([^\s]+)/)
          if (packageMatch && mainWindow) {
            mainWindow.webContents.send('download-progress', {
              step: 5,
              progress: 92,
              status: 'downloading',
              message: `正在下载 ${packageMatch[1]} 包...`,
            })
          }
        } else if (output.includes('Installing')) {
          const packageMatch = output.match(/Installing\s+collected\s+packages:|Successfully\s+installed/)
          if (packageMatch && mainWindow) {
            mainWindow.webContents.send('download-progress', {
              step: 5,
              progress: 93,
              status: 'installing',
              message: '正在安装依赖包...',
            })
          }
        } else if (mainWindow) {
          mainWindow.webContents.send('download-progress', {
            step: 5,
            progress: 92,
            status: 'downloading',
            message: '正在处理依赖包...',
          })
        }
      })

      process.stderr?.on('data', data => {
        const errorOutput = stripAnsiColors(data.toString())
        log.error('Pip error:', errorOutput)
      })

      process.on('close', code => {
        console.log(`pip安装完成，退出码: ${code}`)
        if (code === 0) {
          resolve()
        } else {
          reject(new Error(`依赖安装失败，退出码: ${code}`))
        }
      })

      process.on('error', error => {
        console.error('pip进程错误:', error)
        reject(error)
      })
    })

    // 安装成功后保存当前requirements的哈希值
    saveInstallHash(appRoot, currentHash)

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 5,
        progress: 94,
        status: 'completed',
        message: 'Python 依赖安装完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 5,
        progress: 0,
        status: 'error',
        message: `依赖安装失败: ${errorMessage}`,
      })
    }
    return { success: false, error: errorMessage }
  }
}

// 检查依赖状态
export function checkDependencyStatus(appRoot: string): {
  requirementsExists: boolean
  hasChanged: boolean
  currentHash?: string
  lastHash?: string | null
} {
  const requirementsPath = path.join(appRoot, 'requirements.txt')

  if (!fs.existsSync(requirementsPath)) {
    return {
      requirementsExists: false,
      hasChanged: false
    }
  }

  const { changed, currentHash, lastHash } = checkRequirementsChanged(appRoot)

  return {
    requirementsExists: true,
    hasChanged: changed,
    currentHash,
    lastHash
  }
}

// 强制重新安装依赖
export async function forceReinstallDependencies(
  appRoot: string,
  mirror = 'tsinghua'
): Promise<{
  success: boolean
  error?: string
}> {
  const result = await installDependencies(appRoot, mirror, true)
  return {
    success: result.success,
    error: result.error
  }
}

// 导出pip安装函数
export async function installPipPackage(
  appRoot: string
): Promise<{ success: boolean; error?: string }> {
  try {
    const pythonPath = path.join(appRoot, 'environment', 'python')

    if (!fs.existsSync(pythonPath)) {
      throw new Error('Python环境不存在，请先安装Python')
    }

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'pip',
        progress: 0,
        status: 'installing',
        message: '正在安装pip...',
      })
    }

    await installPip(pythonPath, appRoot)

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'pip',
        progress: 100,
        status: 'completed',
        message: 'pip 安装完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'pip',
        progress: 0,
        status: 'error',
        message: `pip安装失败: ${errorMessage}`,
      })
    }
    return { success: false, error: errorMessage }
  }
}

// 启动后端
let backendProc: ChildProcessWithoutNullStreams | null = null

/**
 * 启动后端
 * @param appRoot 项目根目录
 * @param timeoutMs 等待启动超时（默认 30 秒）
 */
export async function startBackend(appRoot: string, timeoutMs = 30_000) {
  try {
    // 如果已经在运行，直接返回
    if (backendProc && !backendProc.killed && backendProc.exitCode == null) {
      console.log('[Backend] 已在运行, PID =', backendProc.pid)
      return { success: true }
    }

    const pythonExe = path.join(appRoot, 'environment', 'python', 'python.exe')
    const mainPy = path.join(appRoot, 'main.py')

    if (!fs.existsSync(pythonExe)) {
      throw new Error(`Python可执行文件不存在: ${pythonExe}`)
    }
    if (!fs.existsSync(mainPy)) {
      throw new Error(`后端主文件不存在: ${mainPy}`)
    }

    console.log(`[Backend] spawn "${pythonExe}" "${mainPy}" (cwd=${appRoot})`)

    backendProc = spawn(pythonExe, [mainPy], {
      cwd: appRoot,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })

    backendProc.stdout.setEncoding('utf8')
    backendProc.stderr.setEncoding('utf8')

    backendProc.stdout.on('data', d => {
      const line = stripAnsiColors(d.toString().trim())
      if (line) log.info('[Backend]', line)
    })
    backendProc.stderr.on('data', d => {
      const line = stripAnsiColors(d.toString().trim())
      if (line) log.info('[Backend]', line)
    })

    backendProc.once('exit', (code, signal) => {
      console.log('[Backend] 退出', { code, signal })
      backendProc = null
    })
    backendProc.once('error', e => {
      console.error('[Backend] 进程错误:', e)
    })

    // 等待启动成功（匹配 Uvicorn 的输出）
    await new Promise<void>((resolve, reject) => {
      let settled = false
      const timer = setTimeout(() => {
        if (!settled) {
          settled = true
          reject(new Error('后端启动超时'))
        }
      }, timeoutMs)

      const checkReady = (buf: Buffer | string) => {
        if (settled) return
        const s = buf.toString()
        if (/Uvicorn running|http:\/\/0\.0\.0\.0:\d+/.test(s)) {
          settled = true
          clearTimeout(timer)
          resolve()
        }
      }

      backendProc!.stdout.on('data', checkReady)
      backendProc!.stderr.on('data', checkReady)

      backendProc!.once('exit', (code, sig) => {
        if (!settled) {
          settled = true
          clearTimeout(timer)
          reject(new Error(`后端提前退出: code=${code}, signal=${sig ?? ''}`))
        }
      })
      backendProc!.once('error', err => {
        if (!settled) {
          settled = true
          clearTimeout(timer)
          reject(err)
        }
      })
    })

    console.log('[Backend] 启动成功, PID =', backendProc.pid)
    return { success: true }
  } catch (e) {
    console.error('[Backend] 启动失败:', e)
    return { success: false, error: e instanceof Error ? e.message : String(e) }
  }
}

/** 停止后端进程（如果没启动就直接返回成功） */
export async function stopBackend() {
  if (!backendProc || backendProc.killed) {
    console.log('[Backend] 未运行，无需停止')
    return { success: true }
  }

  const pid = backendProc.pid
  console.log('[Backend] 正在停止后端服务, PID =', pid)

  return new Promise<{ success: boolean; error?: string }>(resolve => {
    // 设置超时，确保不会无限等待
    const timeout = setTimeout(() => {
      console.warn('[Backend] 停止超时，强制结束进程')
      try {
        if (backendProc && !backendProc.killed) {
          // 在 Windows 上使用 taskkill 强制结束进程树
          if (process.platform === 'win32') {
            const { exec } = require('child_process')
            exec(`taskkill /f /t /pid ${pid}`, (error: any) => {
              if (error) {
                console.error('[Backend] taskkill 失败:', error)
              } else {
                console.log('[Backend] 进程树已强制结束')
              }
            })
          } else {
            backendProc.kill('SIGKILL')
          }
        }
      } catch (e) {
        console.error('[Backend] 强制结束失败:', e)
      }
      backendProc = null
      resolve({ success: true })
    }, 2000) // 2秒超时

    // 清监听，避免重复日志
    backendProc?.stdout?.removeAllListeners('data')
    backendProc?.stderr?.removeAllListeners('data')

    backendProc!.once('exit', (code, signal) => {
      clearTimeout(timeout)
      console.log('[Backend] 已退出', { code, signal })
      backendProc = null
      resolve({ success: true })
    })

    backendProc!.once('error', err => {
      clearTimeout(timeout)
      console.error('[Backend] 停止时出错:', err)
      backendProc = null
      resolve({ success: false, error: err instanceof Error ? err.message : String(err) })
    })

    try {
      // 首先尝试优雅关闭
      backendProc!.kill('SIGTERM')
      console.log('[Backend] 已发送 SIGTERM 信号')
    } catch (e) {
      clearTimeout(timeout)
      console.error('[Backend] kill 调用失败:', e)
      backendProc = null
      resolve({ success: false, error: e instanceof Error ? e.message : String(e) })
    }
  })
}
