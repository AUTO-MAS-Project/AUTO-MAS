import * as path from 'path'
import * as fs from 'fs'
import { spawn } from 'child_process'
import { BrowserWindow } from 'electron'
import AdmZip from 'adm-zip'
import { downloadFile } from './downloadService'
import { ChildProcessWithoutNullStreams } from 'node:child_process'
import { log, stripAnsiColors } from './logService'


let mainWindow: BrowserWindow | null = null

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
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
    console.log('pip已经安装，跳过安装步骤')
    console.log('检测到pip.exe文件存在，认为pip安装成功')
    console.log('pip检查完成')
    return
  }

  console.log('pip未安装，开始安装...')

  const getPipPath = path.join(pythonPath, 'get-pip.py')
  const getPipUrl = 'https://download.auto-mas.top/d/AUTO_MAS/get-pip.py'

  console.log(`Python可执行文件路径: ${pythonExe}`)
  console.log(`get-pip.py下载URL: ${getPipUrl}`)
  console.log(`get-pip.py保存路径: ${getPipPath}`)

  // 下载get-pip.py
  console.log('开始下载get-pip.py...')
  try {
    await downloadFile(getPipUrl, getPipPath)
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
        message: '开始下载Python...',
      })
    }

    // 根据选择的镜像源获取下载链接
    const pythonUrl =
      pythonMirrorUrls[mirror as keyof typeof pythonMirrorUrls] || pythonMirrorUrls.ustc
    const zipPath = path.join(environmentPath, 'python.zip')

    await downloadFile(pythonUrl, zipPath)

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
        message: 'Python和pip安装完成',
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

// 安装Python依赖
export async function installDependencies(
  appRoot: string,
  mirror = 'tsinghua'
): Promise<{
  success: boolean
  error?: string
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

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'dependencies',
        progress: 0,
        status: 'downloading',
        message: '正在安装Python依赖包...',
      })
    }

    // 获取pip镜像源URL
    const pipMirrorUrl =
      pipMirrorUrls[mirror as keyof typeof pipMirrorUrls] || pipMirrorUrls.tsinghua

    // 使用Scripts文件夹中的pip.exe
    const pythonDir = path.join(appRoot, 'environment', 'python')
    const pipExePath = path.join(pythonDir, 'Scripts', 'pip.exe')

    console.log(`开始安装Python依赖`)
    console.log(`Python目录: ${pythonDir}`)
    console.log(`pip.exe路径: ${pipExePath}`)
    console.log(`requirements.txt路径: ${requirementsPath}`)
    console.log(`pip镜像源: ${pipMirrorUrl}`)

    // 检查pip.exe是否存在
    if (!fs.existsSync(pipExePath)) {
      throw new Error(`pip.exe不存在: ${pipExePath}`)
    }

    // 安装依赖 - 直接使用pip.exe而不是python -m pip
    await new Promise<void>((resolve, reject) => {
      const process = spawn(
        pipExePath,
        [
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

        if (mainWindow) {
          mainWindow.webContents.send('download-progress', {
            type: 'dependencies',
            progress: 50,
            status: 'downloading',
            message: '正在安装依赖包...',
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

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'dependencies',
        progress: 100,
        status: 'completed',
        message: 'Python依赖安装完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        type: 'dependencies',
        progress: 0,
        status: 'error',
        message: `依赖安装失败: ${errorMessage}`,
      })
    }
    return { success: false, error: errorMessage }
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
        message: 'pip安装完成',
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
    // 清监听，避免重复日志
    backendProc?.stdout?.removeAllListeners('data')
    backendProc?.stderr?.removeAllListeners('data')

    backendProc!.once('exit', (code, signal) => {
      console.log('[Backend] 已退出', { code, signal })
      backendProc = null
      resolve({ success: true })
    })

    backendProc!.once('error', err => {
      console.error('[Backend] 停止时出错:', err)
      backendProc = null
      resolve({ success: false, error: err instanceof Error ? err.message : String(err) })
    })

    try {
      backendProc!.kill() // 默认 SIGTERM，Windows 下等价于结束进程
    } catch (e) {
      console.error('[Backend] kill 调用失败:', e)
      backendProc = null
      resolve({ success: false, error: e instanceof Error ? e.message : String(e) })
    }
  })
}
