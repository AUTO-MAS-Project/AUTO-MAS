import * as path from 'path'
import * as fs from 'fs'
import { spawn } from 'child_process'
import { BrowserWindow, app } from 'electron'
import AdmZip from 'adm-zip'
import { downloadFile } from './downloadService'

let mainWindow: BrowserWindow | null = null

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
}

const gitDownloadUrl = 'https://download.auto-mas.top/d/AUTO-MAS/git.zip'

// 默认分支名称（作为备用分支）
const DEFAULT_BRANCH = 'feature/refactor'

// 获取应用版本号
function getAppVersion(appRoot: string): string {
  console.log('=== 开始获取应用版本号 ===')
  console.log(`应用根目录: ${appRoot}`)

  try {
    // 方法1: 从 Electron app 获取版本号（打包后可用      // 6. 强制复制指定文件和文件夹到根目录
    console.log('📋 强制复制文件到根目录...')
    try {
      const appVersion = app.getVersion()
      if (appVersion && appVersion !== '1.0.0') {
        // 避免使用默认版本
        console.log(`✅ 从 app.getVersion() 获取版本号: ${appVersion}`)
        return appVersion
      }
    } catch (error) {
      console.log('⚠️ app.getVersion() 获取失败:', error)
    }

    // 方法2: 从预设的环境变量获取（如果在构建时注入了）
    if (process.env.VITE_APP_VERSION) {
      console.log(`✅ 从环境变量获取版本号: ${process.env.VITE_APP_VERSION}`)
      return process.env.VITE_APP_VERSION
    }

    // 方法3: 开发环境下从 package.json 获取
    const packageJsonPath = path.join(appRoot, 'frontend', 'package.json')
    console.log(`尝试读取前端package.json: ${packageJsonPath}`)

    if (fs.existsSync(packageJsonPath)) {
      const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'))
      const version = packageJson.version || '获取版本失败！'
      console.log(`✅ 从前端package.json获取版本号: ${version}`)
      return version
    }

    console.log('⚠️ 前端package.json不存在，尝试读取根目录package.json')

    // 方法4: 从根目录 package.json 获取（开发环境）
    const currentPackageJsonPath = path.join(appRoot, 'package.json')
    console.log(`尝试读取根目录package.json: ${currentPackageJsonPath}`)

    if (fs.existsSync(currentPackageJsonPath)) {
      const packageJson = JSON.parse(fs.readFileSync(currentPackageJsonPath, 'utf8'))
      const version = packageJson.version || '获取版本失败！'
      console.log(`✅ 从根目录package.json获取版本号: ${version}`)
      return version
    }

    console.log('❌ 未找到任何版本信息源')
    return '获取版本失败！'
  } catch (error) {
    console.error('❌ 获取版本号失败:', error)
    return '获取版本失败！'
  }
}

// 检查分支是否存在
async function checkBranchExists(
  gitPath: string,
  gitEnv: any,
  repoUrl: string,
  branchName: string
): Promise<boolean> {
  console.log(`=== 检查分支是否存在: ${branchName} ===`)
  console.log(`Git路径: ${gitPath}`)
  console.log(`仓库URL: ${repoUrl}`)

  try {
    return new Promise<boolean>(resolve => {
      const proc = spawn(gitPath, ['ls-remote', '--heads', repoUrl, branchName], {
        stdio: 'pipe',
        env: gitEnv,
      })

      let output = ''
      let errorOutput = ''

      proc.stdout?.on('data', data => {
        const chunk = data.toString()
        output += chunk
        console.log(`git ls-remote stdout: ${chunk.trim()}`)
      })

      proc.stderr?.on('data', data => {
        const chunk = data.toString()
        errorOutput += chunk
        console.log(`git ls-remote stderr: ${chunk.trim()}`)
      })

      proc.on('close', code => {
        console.log(`git ls-remote 退出码: ${code}`)
        // 如果输出包含分支名，说明分支存在
        const branchExists = output.includes(`refs/heads/${branchName}`)
        console.log(`分支 ${branchName} ${branchExists ? '✅ 存在' : '❌ 不存在'}`)
        if (errorOutput) {
          console.log(`错误输出: ${errorOutput}`)
        }
        resolve(branchExists)
      })

      proc.on('error', error => {
        console.error(`git ls-remote 进程错误:`, error)
        resolve(false)
      })
    })
  } catch (error) {
    console.error(`❌ 检查分支 ${branchName} 时出错:`, error)
    return false
  }
}

// 递归复制目录，包括文件和隐藏文件（完全替换模式）
function copyDirSync(src: string, dest: string) {
  // 确保目标目录存在
  if (!fs.existsSync(dest)) {
    fs.mkdirSync(dest, { recursive: true })
  }
  
  const entries = fs.readdirSync(src, { withFileTypes: true })
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name)
    const destPath = path.join(dest, entry.name)
    
    if (entry.isDirectory()) {
      // 递归复制子目录
      copyDirSync(srcPath, destPath)
    } else {
      // 复制文件（直接覆盖）
      fs.copyFileSync(srcPath, destPath)
    }
  }
}

// 清理本地老分支（保留指定分支）
async function cleanOldLocalBranches(
  gitPath: string,
  gitEnv: any,
  repoPath: string,
  currentBranch: string,
  defaultBranch: string
): Promise<void> {
  console.log('=== 开始清理本地老分支 ===')
  console.log(`当前分支: ${currentBranch}`)
  console.log(`默认分支: ${defaultBranch}`)

  try {
    // 1. 获取所有本地分支
    const localBranches = await new Promise<string[]>(resolve => {
      const proc = spawn(gitPath, ['branch', '--format=%(refname:short)'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
        if (code === 0) {
          const branches = output
            .split('\n')
            .map(line => line.trim())
            .filter(line => line && !line.startsWith('*'))
          console.log(`发现本地分支: ${branches.join(', ')}`)
          resolve(branches)
        } else {
          console.log('⚠️ 获取本地分支失败')
          resolve([])
        }
      })

      proc.on('error', error => {
        console.log('⚠️ 获取本地分支出错:', error)
        resolve([])
      })
    })

    // 2. 确定需要保留的分支
    const branchesToKeep = new Set([currentBranch, defaultBranch])
    console.log(`需要保留的分支: ${Array.from(branchesToKeep).join(', ')}`)

    // 3. 找出需要删除的分支
    const branchesToDelete = localBranches.filter(branch => !branchesToKeep.has(branch))

    if (branchesToDelete.length === 0) {
      console.log('✅ 没有需要清理的老分支')
      return
    }

    console.log(`需要删除的老分支: ${branchesToDelete.join(', ')}`)

    // 4. 删除老分支
    for (const branch of branchesToDelete) {
      console.log(`🗑️ 删除分支: ${branch}`)
      await new Promise<void>(resolve => {
        const proc = spawn(gitPath, ['branch', '-D', branch], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })

        proc.stdout?.on('data', data => {
          console.log(`删除分支 ${branch} stdout:`, data.toString().trim())
        })

        proc.stderr?.on('data', data => {
          console.log(`删除分支 ${branch} stderr:`, data.toString().trim())
        })

        proc.on('close', code => {
          if (code === 0) {
            console.log(`✅ 成功删除分支: ${branch}`)
          } else {
            console.log(`⚠️ 删除分支 ${branch} 失败，但继续`)
          }
          resolve()
        })

        proc.on('error', error => {
          console.log(`⚠️ 删除分支 ${branch} 出错:`, error)
          resolve()
        })
      })
    }

    console.log('✅ 本地老分支清理完成')
  } catch (error) {
    console.error('❌ 清理本地老分支失败:', error)
    // 不抛出错误，继续执行后续步骤
  }
}

// 强制复制指定的文件和文件夹到目标目录（强制替换）
async function copySelectedFiles(sourcePath: string, targetPath: string, branchName: string) {
  console.log(`=== 开始强制复制选定文件（完全替换模式） ===`)
  console.log(`源路径: ${sourcePath}`)
  console.log(`目标路径: ${targetPath}`)
  console.log(`分支: ${branchName}`)
  console.log(`⚠️  注意: 此操作将完全删除目标文件/目录后重新复制，确保清理多余文件`)

  // 需要复制的文件和文件夹列表
  const itemsToCopy = ['app', 'res', 'main.py', 'requirements.txt', 'LICENSE', 'README.md', '.git']

  let successCount = 0
  let skipCount = 0

  for (const item of itemsToCopy) {
    const srcPath = path.join(sourcePath, item)
    const dstPath = path.join(targetPath, item)

    if (!fs.existsSync(srcPath)) {
      console.log(`⚠️ 源文件/目录不存在，跳过: ${item}`)
      skipCount++
      continue
    }

    console.log(`🔄 强制复制: ${item}`)

    try {
      const isSourceDir = fs.statSync(srcPath).isDirectory()

      // 强制删除目标文件/目录（如果存在）
      if (fs.existsSync(dstPath)) {
        const isTargetDir = fs.statSync(dstPath).isDirectory()
        console.log(`  - 🗑️ 强制删除现有${isTargetDir ? '目录' : '文件'}: ${item}`)
        
        if (isTargetDir) {
          fs.rmSync(dstPath, { recursive: true, force: true })
        } else {
          fs.unlinkSync(dstPath)
        }
      }

      // 强制复制文件或目录
      if (isSourceDir) {
        console.log(`  - 📁 完全替换复制目录: ${item}`)
        // 确保目标目录不存在，然后完整复制
        copyDirSync(srcPath, dstPath)
      } else {
        console.log(`  - 📄 强制复制文件: ${item}`)
        fs.copyFileSync(srcPath, dstPath)
      }

      console.log(`  ✅ 强制复制完成: ${item}`)
      successCount++
    } catch (error) {
      console.error(`  ❌ 强制复制失败: ${item}`, error)
      throw error
    }
  }

  console.log(
    `✅ 强制复制操作完成 - 成功: ${successCount}, 跳过: ${skipCount}, 总计: ${itemsToCopy.length}`
  )
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

// 检查网络连接（通过访问GitHub来测试）
async function checkNetworkConnection(gitPath: string, gitEnv: any, repoUrl: string): Promise<boolean> {
  console.log('=== 检查网络连接 ===')
  try {
    return new Promise<boolean>(resolve => {
      const proc = spawn(gitPath, ['ls-remote', '--heads', repoUrl], {
        stdio: 'pipe',
        env: gitEnv,
      })
      
      let hasOutput = false
      proc.stdout?.on('data', () => {
        hasOutput = true
      })
      
      proc.on('close', code => {
        const isConnected = code === 0 && hasOutput
        console.log(`网络连接检查 - 退出码: ${code}, 有输出: ${hasOutput}, 连接状态: ${isConnected ? '正常' : '异常'}`)
        resolve(isConnected)
      })
      
      proc.on('error', error => {
        console.log('网络连接检查进程错误:', error)
        resolve(false)
      })
      
      // 5秒超时
      setTimeout(() => {
        proc.kill()
        console.log('网络连接检查超时')
        resolve(false)
      }, 5000)
    })
  } catch (error) {
    console.error('网络连接检查异常:', error)
    return false
  }
}

// 下载Git
// 检查repo目录状态
export async function checkRepoStatus(appRoot: string): Promise<{
  exists: boolean
  isGitRepo: boolean
  currentBranch?: string
  currentCommit?: string
  error?: string
}> {
  try {
    const repoPath = path.join(appRoot, 'repo')

    // 检查repo目录是否存在
    if (!fs.existsSync(repoPath)) {
      console.log('repo目录不存在')
      return { exists: false, isGitRepo: false }
    }

    // 检查是否为git仓库
    const gitDir = path.join(repoPath, '.git')
    if (!fs.existsSync(gitDir)) {
      console.log('repo目录存在但不是git仓库')
      return { exists: true, isGitRepo: false }
    }

    // 获取Git环境和路径
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
    if (!fs.existsSync(gitPath)) {
      return { exists: true, isGitRepo: true, error: 'Git可执行文件不存在' }
    }

    const gitEnv = getGitEnvironment(appRoot)

    // 获取当前分支和commit信息
    const [currentBranch, currentCommit] = await Promise.all([
      new Promise<string>(resolve => {
        const proc = spawn(gitPath, ['branch', '--show-current'], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        let output = ''
        proc.stdout?.on('data', data => {
          output += data.toString()
        })
        proc.on('close', () => resolve(output.trim() || 'unknown'))
        proc.on('error', () => resolve('unknown'))
      }),
      new Promise<string>(resolve => {
        const proc = spawn(gitPath, ['rev-parse', 'HEAD'], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        let output = ''
        proc.stdout?.on('data', data => {
          output += data.toString()
        })
        proc.on('close', () => resolve(output.trim() || 'unknown'))
        proc.on('error', () => resolve('unknown'))
      }),
    ])

    console.log(`repo状态 - 分支: ${currentBranch}, commit: ${currentCommit.substring(0, 8)}`)

    return {
      exists: true,
      isGitRepo: true,
      currentBranch,
      currentCommit: currentCommit.substring(0, 8),
    }
  } catch (error) {
    console.error('检查repo状态失败:', error)
    return {
      exists: false,
      isGitRepo: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

// 清理repo目录
export async function cleanRepo(appRoot: string): Promise<{ success: boolean; error?: string }> {
  try {
    const repoPath = path.join(appRoot, 'repo')

    if (fs.existsSync(repoPath)) {
      console.log(`清理repo目录: ${repoPath}`)
      fs.rmSync(repoPath, { recursive: true, force: true })
      console.log('✅ repo目录清理完成')
    } else {
      console.log('repo目录不存在，无需清理')
    }

    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    console.error('清理repo目录失败:', errorMessage)
    return { success: false, error: errorMessage }
  }
}

// 获取repo信息（用于调试和状态显示）
export async function getRepoInfo(appRoot: string): Promise<{
  success: boolean
  info?: {
    repoExists: boolean
    isGitRepo: boolean
    currentBranch?: string
    currentCommit?: string
    remoteUrl?: string
    lastUpdate?: string
  }
  error?: string
}> {
  try {
    const repoPath = path.join(appRoot, 'repo')

    const info = {
      repoExists: fs.existsSync(repoPath),
      isGitRepo: fs.existsSync(path.join(repoPath, '.git')),
    }

    if (info.isGitRepo) {
      const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
      if (fs.existsSync(gitPath)) {
        const gitEnv = getGitEnvironment(appRoot)

        // 获取详细信息
        const [branch, commit, remoteUrl] = await Promise.all([
          new Promise<string>(resolve => {
            const proc = spawn(gitPath, ['branch', '--show-current'], {
              stdio: 'pipe',
              env: gitEnv,
              cwd: repoPath,
            })
            let output = ''
            proc.stdout?.on('data', data => {
              output += data.toString()
            })
            proc.on('close', () => resolve(output.trim() || 'unknown'))
            proc.on('error', () => resolve('unknown'))
          }),
          new Promise<string>(resolve => {
            const proc = spawn(gitPath, ['rev-parse', 'HEAD'], {
              stdio: 'pipe',
              env: gitEnv,
              cwd: repoPath,
            })
            let output = ''
            proc.stdout?.on('data', data => {
              output += data.toString()
            })
            proc.on('close', () => resolve(output.trim().substring(0, 8) || 'unknown'))
            proc.on('error', () => resolve('unknown'))
          }),
          new Promise<string>(resolve => {
            const proc = spawn(gitPath, ['remote', 'get-url', 'origin'], {
              stdio: 'pipe',
              env: gitEnv,
              cwd: repoPath,
            })
            let output = ''
            proc.stdout?.on('data', data => {
              output += data.toString()
            })
            proc.on('close', () => resolve(output.trim() || 'unknown'))
            proc.on('error', () => resolve('unknown'))
          }),
        ])

        // 获取最后更新时间（.git/FETCH_HEAD文件的修改时间）
        let lastUpdate = 'unknown'
        try {
          const fetchHeadPath = path.join(repoPath, '.git', 'FETCH_HEAD')
          if (fs.existsSync(fetchHeadPath)) {
            const stats = fs.statSync(fetchHeadPath)
            lastUpdate = stats.mtime.toLocaleString()
          }
        } catch (e) {
          // 忽略错误
        }

        return {
          success: true,
          info: {
            ...info,
            currentBranch: branch,
            currentCommit: commit,
            remoteUrl,
            lastUpdate,
          },
        }
      }
    }

    return { success: true, info }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    console.error('获取repo信息失败:', errorMessage)
    return { success: false, error: errorMessage }
  }
}

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
  repoUrl = 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git'
): Promise<{
  success: boolean
  error?: string
}> {
  console.log('=== 开始克隆/更新后端代码 ===')
  console.log(`应用根目录: ${appRoot}`)
  console.log(`仓库URL: ${repoUrl}`)

  try {
    const repoPath = path.join(appRoot, 'repo')
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')

    console.log(`Git可执行文件路径: ${gitPath}`)
    console.log(`仓库路径: ${repoPath}`)

    if (!fs.existsSync(gitPath)) {
      const error = `Git可执行文件不存在: ${gitPath}`
      console.error(`❌ ${error}`)
      throw new Error(error)
    }

    console.log('✅ Git可执行文件存在')
    const gitEnv = getGitEnvironment(appRoot)
    console.log('✅ Git环境变量配置完成')

    // 检查 git 是否可用
    console.log('=== 检查Git是否可用 ===')
    await new Promise<void>((resolve, reject) => {
      const proc = spawn(gitPath, ['--version'], { env: gitEnv })

      proc.stdout?.on('data', data => {
        console.log(`git --version output: ${data.toString().trim()}`)
      })

      proc.stderr?.on('data', data => {
        console.log(`git --version error: ${data.toString().trim()}`)
      })

      proc.on('close', code => {
        console.log(`git --version 退出码: ${code}`)
        if (code === 0) {
          console.log('✅ Git可用')
          resolve()
        } else {
          console.error('❌ Git无法正常运行')
          reject(new Error('git 无法正常运行'))
        }
      })

      proc.on('error', error => {
        console.error('❌ Git进程启动失败:', error)
        reject(error)
      })
    })

    // 检查网络连接
    console.log('=== 检查网络连接 ===')
    const isNetworkAvailable = await checkNetworkConnection(gitPath, gitEnv, repoUrl)
    if (!isNetworkAvailable) {
      throw new Error('网络连接不可用，请检查网络连接后重试')
    }
    console.log('✅ 网络连接正常')

    // 获取版本号并确定目标分支
    const version = getAppVersion(appRoot)
    console.log(`=== 分支选择逻辑 ===`)
    console.log(`当前应用版本: ${version}`)

    let targetBranch = 'feature/refactor' // 默认分支
    console.log(`默认分支: ${targetBranch}`)

    if (version !== '获取版本失败！') {
      // 检查版本对应的分支是否存在
      console.log(`开始检查版本分支是否存在...`)
      const versionBranchExists = await checkBranchExists(gitPath, gitEnv, repoUrl, version)
      if (versionBranchExists) {
        targetBranch = version
        console.log(`🎯 将使用版本分支: ${targetBranch}`)
      } else {
        console.log(`⚠️ 版本分支 ${version} 不存在，使用默认分支: ${targetBranch}`)
      }
    } else {
      console.log('⚠️ 版本号获取失败，使用默认分支: feature/refactor')
    }

    console.log(`=== 最终选择分支: ${targetBranch} ===`)

    // 检查是否为Git仓库
    const isRepo = isGitRepository(repoPath)
    console.log(`检查是否为Git仓库: ${isRepo ? '✅ 是' : '❌ 否'}`)

    // ==== 下面是关键逻辑 ====
    if (isRepo) {
      console.log('=== 更新现有Git仓库 ===')

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: `正在更新后端代码(分支: ${targetBranch})...`,
        })
      }

      // 1. 动态配置git仓库fetch范围（仅目标分支和默认分支）
      const branchesToFetch =
        targetBranch === DEFAULT_BRANCH ? [targetBranch] : [targetBranch, DEFAULT_BRANCH]

      console.log(`🔧 配置git仓库fetch范围: ${branchesToFetch.join(', ')}...`)

      // 构建 fetch refspec
      const refspecs = branchesToFetch.map(
        branch => `+refs/heads/${branch}:refs/remotes/origin/${branch}`
      )

      // 先清理现有的fetch配置
      await new Promise<void>((resolve) => {
        const proc = spawn(gitPath, ['config', '--unset-all', 'remote.origin.fetch'], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        proc.stdout?.on('data', d => console.log('git config --unset-all stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => console.log('git config --unset-all stderr:', d.toString().trim()))
        proc.on('close', code => {
          console.log(`git config --unset-all 退出码: ${code}`)
          if (code === 0) {
            console.log(`✅ 清理现有fetch配置成功`)
          } else {
            console.log(`⚠️ 清理现有fetch配置失败或无配置需要清理`)
          }
          resolve() // 无论成功失败都继续
        })
        proc.on('error', error => {
          console.log('⚠️ git config --unset-all 进程错误，但继续执行:', error)
          resolve()
        })
      })

      // 重新设置fetch配置
      for (const refspec of refspecs) {
        await new Promise<void>((resolve) => {
          const proc = spawn(gitPath, ['config', '--add', 'remote.origin.fetch', refspec], {
            stdio: 'pipe',
            env: gitEnv,
            cwd: repoPath,
          })
          proc.stdout?.on('data', d => console.log('git config --add stdout:', d.toString().trim()))
          proc.stderr?.on('data', d => console.log('git config --add stderr:', d.toString().trim()))
          proc.on('close', code => {
            console.log(`git config --add 退出码: ${code}`)
            if (code === 0) {
              console.log(`✅ 添加fetch配置成功: ${refspec}`)
            } else {
              console.log(`⚠️ 添加fetch配置失败: ${refspec}`)
            }
            resolve()
          })
          proc.on('error', error => {
            console.log('⚠️ git config --add 进程错误:', error)
            resolve()
          })
        })
      }

      // 2. 只获取指定分支的远程信息
      console.log(`📥 获取指定分支的远程信息: ${branchesToFetch.join(', ')}...`)

      // 逐个获取指定分支（关键操作，失败时抛出错误）
      let fetchSuccessCount = 0
      for (const branch of branchesToFetch) {
        console.log(`📥 获取分支: ${branch}`)
        await new Promise<void>((resolve, reject) => {
          const proc = spawn(gitPath, ['fetch', 'origin', branch, '--force'], {
            stdio: 'pipe',
            env: gitEnv,
            cwd: repoPath,
          })
          
          let errorOutput = ''
          proc.stdout?.on('data', d =>
            console.log(`git fetch ${branch} stdout:`, d.toString().trim())
          )
          proc.stderr?.on('data', d => {
            const stderr = d.toString().trim()
            console.log(`git fetch ${branch} stderr:`, stderr)
            errorOutput += stderr
          })
          
          proc.on('close', code => {
            console.log(`git fetch ${branch} 退出码: ${code}`)
            if (code === 0) {
              console.log(`✅ 成功获取分支: ${branch}`)
              fetchSuccessCount++
              resolve()
            } else {
              console.error(`❌ 获取分支 ${branch} 失败`)
              const isNetworkError = errorOutput.includes('unable to access') || 
                                   errorOutput.includes('Could not resolve host') ||
                                   errorOutput.includes('Connection refused') ||
                                   errorOutput.includes('network is unreachable')
              if (isNetworkError) {
                reject(new Error(`网络连接失败: 无法获取分支 ${branch}`))
              } else {
                reject(new Error(`获取分支 ${branch} 失败: ${errorOutput}`))
              }
            }
          })
          
          proc.on('error', error => {
            console.error(`❌ git fetch ${branch} 进程错误:`, error)
            reject(error)
          })
        })
      }
      
      if (fetchSuccessCount === 0) {
        throw new Error('所有分支获取都失败，可能是网络问题')
      }

      console.log(`✅ 指定分支获取完成`)

      // 3. 强制切换到目标分支并设置远程跟踪
      console.log(`🔀 强制切换到目标分支: ${targetBranch}`)
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['checkout', '-B', targetBranch, `origin/${targetBranch}`], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        proc.stdout?.on('data', d => console.log('git checkout stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => console.log('git checkout stderr:', d.toString().trim()))
        proc.on('close', code => {
          console.log(`git checkout 退出码: ${code}`)
          if (code === 0) {
            console.log(`✅ 成功切换到分支: ${targetBranch}`)
            resolve()
          } else {
            console.error(`❌ 切换分支失败: ${targetBranch}`)
            reject(new Error(`git checkout失败，退出码: ${code}`))
          }
        })
        proc.on('error', error => {
          console.error('❌ git checkout 进程错误:', error)
          reject(error)
        })
      })

      // 4. 设置上游分支跟踪
      console.log(`🔗 设置分支上游跟踪: ${targetBranch} -> origin/${targetBranch}`)
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(
          gitPath,
          ['branch', '--set-upstream-to', `origin/${targetBranch}`, targetBranch],
          {
            stdio: 'pipe',
            env: gitEnv,
            cwd: repoPath,
          }
        )
        proc.stdout?.on('data', d =>
          console.log('git branch --set-upstream stdout:', d.toString().trim())
        )
        proc.stderr?.on('data', d =>
          console.log('git branch --set-upstream stderr:', d.toString().trim())
        )
        proc.on('close', code => {
          console.log(`git branch --set-upstream 退出码: ${code}`)
          if (code === 0) {
            console.log(`✅ 成功设置上游分支跟踪`)
          } else {
            console.log(`⚠️ 设置上游分支跟踪失败，但继续执行`)
          }
          resolve() // 无论成功失败都继续
        })
        proc.on('error', error => {
          console.log('⚠️ git branch --set-upstream 进程错误，但继续执行:', error)
          resolve()
        })
      })

      // 5. 强制同步到远程最新代码（远端优先，解决所有冲突）
      console.log('🔄 强制同步到远程分支最新代码（远端优先）...')
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['reset', '--hard', `origin/${targetBranch}`], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        proc.stdout?.on('data', d => console.log('git reset stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => console.log('git reset stderr:', d.toString().trim()))
        proc.on('close', code => {
          console.log(`git reset --hard 退出码: ${code}`)
          if (code === 0) {
            console.log('✅ 代码已强制更新到远程最新版本（远端优先）')
            resolve()
          } else {
            console.error('❌ 代码强制同步失败')
            reject(new Error(`git reset --hard 失败，退出码: ${code}`))
          }
        })
        proc.on('error', error => {
          console.error('❌ git reset 进程错误:', error)
          reject(error)
        })
      })

      // 6. 清理本地老分支（保留当前分支和默认分支）
      console.log('🧹 清理本地老分支...')
      await cleanOldLocalBranches(gitPath, gitEnv, repoPath, targetBranch, DEFAULT_BRANCH)

      // 7. 复制指定文件和文件夹到根目录
      console.log('📋 复制文件到根目录...')
      await copySelectedFiles(repoPath, appRoot, targetBranch)

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 100,
          status: 'completed',
          message: `后端代码更新完成(分支: ${targetBranch})`,
        })
      }

      console.log(`✅ 后端代码更新完成(分支: ${targetBranch})`)
    } else {
      console.log('=== 克隆新的Git仓库 ===')

      // 不是 git 仓库，直接克隆到 repo 目录
      console.log(`仓库目录: ${repoPath}`)

      if (fs.existsSync(repoPath)) {
        console.log('🗑️ 清理现有仓库目录...')
        fs.rmSync(repoPath, { recursive: true, force: true })
      }

      console.log('📁 创建仓库目录...')
      fs.mkdirSync(repoPath, { recursive: true })

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: `正在克隆后端代码(分支: ${targetBranch})...`,
        })
      }

      console.log(`📥 开始克隆代码到仓库目录...`)
      console.log(`克隆参数: --single-branch --branch ${targetBranch} (只克隆目标分支)`)

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
            targetBranch,
            repoUrl,
            repoPath,
          ],
          {
            stdio: 'pipe',
            env: gitEnv,
            cwd: appRoot,
          }
        )
        
        let errorOutput = ''
        proc.stdout?.on('data', d => console.log('git clone stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => {
          const stderr = d.toString().trim()
          console.log('git clone stderr:', stderr)
          errorOutput += stderr
        })
        
        proc.on('close', code => {
          console.log(`git clone 退出码: ${code}`)
          if (code === 0) {
            console.log('✅ 代码克隆成功')
            resolve()
          } else {
            console.error('❌ 代码克隆失败')
            const isNetworkError = errorOutput.includes('unable to access') || 
                                 errorOutput.includes('Could not resolve host') ||
                                 errorOutput.includes('Connection refused') ||
                                 errorOutput.includes('network is unreachable')
            if (isNetworkError) {
              reject(new Error(`网络连接失败: 无法克隆代码仓库`))
            } else {
              reject(new Error(`代码克隆失败: ${errorOutput}`))
            }
          }
        })
        
        proc.on('error', error => {
          console.error('❌ git clone 进程错误:', error)
          reject(error)
        })
      })

      // 克隆后配置额外分支获取（如果需要）
      if (targetBranch !== DEFAULT_BRANCH) {
        console.log(`🔧 添加默认分支 ${DEFAULT_BRANCH} 的fetch配置...`)
        await new Promise<void>(resolve => {
          const proc = spawn(
            gitPath,
            [
              'config',
              '--add',
              'remote.origin.fetch',
              `+refs/heads/${DEFAULT_BRANCH}:refs/remotes/origin/${DEFAULT_BRANCH}`,
            ],
            {
              stdio: 'pipe',
              env: gitEnv,
              cwd: repoPath,
            }
          )
          proc.on('close', code => {
            console.log(`添加默认分支配置退出码: ${code}`)
            if (code === 0) {
              console.log(`✅ 成功添加默认分支 ${DEFAULT_BRANCH} 的fetch配置`)
            } else {
              console.log(`⚠️ 添加默认分支配置失败`)
            }
            resolve()
          })
          proc.on('error', error => {
            console.log('⚠️ 添加默认分支配置错误:', error)
            resolve()
          })
        })

        // 获取默认分支（非关键操作，失败不影响主流程）
        console.log(`📥 获取默认分支 ${DEFAULT_BRANCH}...`)
        await new Promise<void>(resolve => {
          const proc = spawn(gitPath, ['fetch', 'origin', DEFAULT_BRANCH], {
            stdio: 'pipe',
            env: gitEnv,
            cwd: repoPath,
          })
          proc.stdout?.on('data', d =>
            console.log(`fetch ${DEFAULT_BRANCH} stdout:`, d.toString().trim())
          )
          proc.stderr?.on('data', d =>
            console.log(`fetch ${DEFAULT_BRANCH} stderr:`, d.toString().trim())
          )
          proc.on('close', code => {
            console.log(`fetch ${DEFAULT_BRANCH} 退出码: ${code}`)
            if (code === 0) {
              console.log(`✅ 成功获取默认分支 ${DEFAULT_BRANCH}`)
            } else {
              console.log(`⚠️ 获取默认分支 ${DEFAULT_BRANCH} 失败，但不影响主流程`)
            }
            resolve()
          })
          proc.on('error', error => {
            console.log(`⚠️ fetch ${DEFAULT_BRANCH} 错误:`, error)
            resolve()
          })
        })
      }

      // 2. 清理本地老分支（保留当前分支和默认分支）
      console.log('🧹 清理本地老分支...')
      await cleanOldLocalBranches(gitPath, gitEnv, repoPath, targetBranch, DEFAULT_BRANCH)

      // 3. 强制复制指定文件和文件夹到根目录
      console.log('📋 强制复制文件到根目录...')
      await copySelectedFiles(repoPath, appRoot, targetBranch)

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 100,
          status: 'completed',
          message: `后端代码克隆完成(分支: ${targetBranch})`,
        })
      }

      console.log(`✅ 后端代码克隆完成(分支: ${targetBranch})`)
    }

    console.log('=== 后端代码获取操作完成 ===')
    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    console.error('❌ 获取后端代码失败:', errorMessage)
    console.error('错误堆栈:', error instanceof Error ? error.stack : 'N/A')

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
