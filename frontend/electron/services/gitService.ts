import * as path from 'path'
import * as fs from 'fs'
import { spawn } from 'child_process'
import { BrowserWindow, app } from 'electron'
import AdmZip from 'adm-zip'
import { downloadFile, downloadFileMultiThread } from './downloadService'

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

const gitDownloadUrl = 'https://download.auto-mas.top/d/AUTO-MAS/git.zip'

// 默认分支名称（作为备用分支）
const DEFAULT_BRANCH = 'dev'

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

// 优化存储：删除不必要的 git 对象和引用
async function optimizeGitStorage(
  gitPath: string,
  gitEnv: any,
  repoPath: string
): Promise<void> {
  console.log('=== 开始优化 Git 存储 ===')

  try {
    // 1. 删除所有 reflog（引用日志）
    console.log('🗑️ 删除所有 reflog...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['reflog', 'expire', '--expire=now', '--all'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      proc.stdout?.on('data', data => {
        console.log(`reflog expire stdout:`, data.toString().trim())
      })

      proc.stderr?.on('data', data => {
        console.log(`reflog expire stderr:`, data.toString().trim())
      })

      proc.on('close', code => {
        if (code === 0) {
          console.log('✅ reflog 删除完成')
        } else {
          console.log('⚠️ reflog 删除失败，但继续')
        }
        resolve()
      })

      proc.on('error', error => {
        console.log('⚠️ reflog 删除出错:', error)
        resolve()
      })
    })

    // 2. 删除所有标签
    console.log('🗑️ 删除所有标签...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['tag', '-l'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
        if (code === 0 && output.trim()) {
          const tags = output.split('\n').filter(tag => tag.trim())
          if (tags.length > 0) {
            console.log(`发现标签: ${tags.join(', ')}`)
            // 删除所有标签
            const deleteProc = spawn(gitPath, ['tag', '-d', ...tags], {
              stdio: 'pipe',
              env: gitEnv,
              cwd: repoPath,
            })
            deleteProc.on('close', deleteCode => {
              if (deleteCode === 0) {
                console.log('✅ 所有标签删除完成')
              } else {
                console.log('⚠️ 标签删除失败，但继续')
              }
              resolve()
            })
            deleteProc.on('error', () => resolve())
          } else {
            console.log('✅ 没有标签需要删除')
            resolve()
          }
        } else {
          console.log('✅ 没有标签需要删除')
          resolve()
        }
      })

      proc.on('error', error => {
        console.log('⚠️ 获取标签列表出错:', error)
        resolve()
      })
    })

    // 3. 强制垃圾回收和压缩
    console.log('🧹 执行强制垃圾回收和压缩...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['gc', '--aggressive', '--prune=now'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      proc.stdout?.on('data', data => {
        console.log(`gc stdout:`, data.toString().trim())
      })

      proc.stderr?.on('data', data => {
        console.log(`gc stderr:`, data.toString().trim())
      })

      proc.on('close', code => {
        if (code === 0) {
          console.log('✅ 垃圾回收和压缩完成')
        } else {
          console.log('⚠️ 垃圾回收失败，但继续')
        }
        resolve()
      })

      proc.on('error', error => {
        console.log('⚠️ 垃圾回收出错:', error)
        resolve()
      })
    })

    console.log('✅ Git 存储优化完成')
  } catch (error) {
    console.error('❌ Git 存储优化失败:', error)
  }
}

// 配置浅克隆仓库，只跟踪指定分支
async function configureShallowRepository(
  gitPath: string,
  gitEnv: any,
  repoPath: string,
  targetBranch: string
): Promise<void> {
  console.log(`🔧 配置浅克隆仓库，只跟踪分支: ${targetBranch}`)

  try {
    // 设置只拉取目标分支的配置
    const targetRefspec = `+refs/heads/${targetBranch}:refs/remotes/origin/${targetBranch}`
    await new Promise<void>((resolve) => {
      const proc = spawn(gitPath, ['config', '--add', 'remote.origin.fetch', targetRefspec], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.stdout?.on('data', d => console.log('git config --add stdout:', d.toString().trim()))
      proc.stderr?.on('data', d => console.log('git config --add stderr:', d.toString().trim()))
      proc.on('close', code => {
        console.log(`git config --add 退出码: ${code}`)
        if (code === 0) {
          console.log(`✅ 设置目标分支fetch配置成功: ${targetRefspec}`)
        } else {
          console.log(`⚠️ 设置目标分支fetch配置失败: ${targetRefspec}`)
        }
        resolve()
      })
      proc.on('error', error => {
        console.log('⚠️ git config --add 进程错误:', error)
        resolve()
      })
    })

    // 设置浅克隆相关配置
    const shallowConfigs = [
      ['core.preloadindex', 'true'],
      ['core.fscache', 'true'],
      ['gc.auto', '0'],  // 禁用自动垃圾回收
      ['fetch.prune', 'true'],  // 自动清理远程已删除的分支
      ['fetch.pruneTags', 'true'],  // 自动清理远程已删除的标签
    ]

    for (const [key, value] of shallowConfigs) {
      await new Promise<void>((resolve) => {
        const proc = spawn(gitPath, ['config', key, value], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        proc.on('close', code => {
          if (code === 0) {
            console.log(`✅ 设置配置 ${key}=${value}`)
          } else {
            console.log(`⚠️ 设置配置 ${key}=${value} 失败`)
          }
          resolve()
        })
        proc.on('error', () => resolve())
      })
    }

    console.log('✅ 浅克隆仓库配置完成')
  } catch (error) {
    console.error('❌ 配置浅克隆仓库失败:', error)
  }
}

// 极致优化拉取后的存储清理
async function optimizePostPullStorage(
  gitPath: string,
  gitEnv: any,
  repoPath: string,
  targetBranch: string
): Promise<void> {
  console.log('=== 开始拉取后极致存储优化 ===')
  console.log(`目标分支: ${targetBranch}`)

  try {
    // 1. 删除除目标分支外的所有本地分支
    console.log('🗑️ 删除其他本地分支...')
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
            .filter(line => line && line !== targetBranch)
          resolve(branches)
        } else {
          resolve([])
        }
      })
      proc.on('error', () => resolve([]))
    })

    for (const branch of localBranches) {
      console.log(`🗑️ 删除分支: ${branch}`)
      await new Promise<void>(resolve => {
        const proc = spawn(gitPath, ['branch', '-D', branch], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        proc.on('close', () => resolve())
        proc.on('error', () => resolve())
      })
    }

    // 2. 删除除目标分支外的所有远程跟踪分支
    console.log('🗑️ 删除其他远程跟踪分支...')
    const remoteRefs = await new Promise<string[]>(resolve => {
      const proc = spawn(gitPath, ['for-each-ref', '--format=%(refname)', 'refs/remotes'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
        if (code === 0 && output.trim()) {
          const refs = output.split('\n')
            .filter(ref => ref.trim())
            .filter(ref => !ref.includes(`refs/remotes/origin/${targetBranch}`))
          resolve(refs)
        } else {
          resolve([])
        }
      })
      proc.on('error', () => resolve([]))
    })

    for (const ref of remoteRefs) {
      await new Promise<void>(resolve => {
        const proc = spawn(gitPath, ['update-ref', '-d', ref], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        proc.on('close', () => resolve())
        proc.on('error', () => resolve())
      })
    }

    // 3. 删除所有标签
    console.log('🗑️ 删除所有标签...')
    const tags = await new Promise<string[]>(resolve => {
      const proc = spawn(gitPath, ['tag', '-l'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
        if (code === 0 && output.trim()) {
          const tagList = output.split('\n').filter(tag => tag.trim())
          resolve(tagList)
        } else {
          resolve([])
        }
      })
      proc.on('error', () => resolve([]))
    })

    if (tags.length > 0) {
      await new Promise<void>(resolve => {
        const proc = spawn(gitPath, ['tag', '-d', ...tags], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        proc.on('close', () => {
          console.log('✅ 所有标签删除完成')
          resolve()
        })
        proc.on('error', () => resolve())
      })
    }

    // 4. 删除所有reflog
    console.log('🗑️ 删除所有reflog...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['reflog', 'expire', '--expire=now', '--all'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => {
        console.log('✅ reflog删除完成')
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 5. 确保仓库为浅克隆状态
    console.log('🔄 确保仓库为浅克隆状态...')
    const currentCommitHash = await new Promise<string>(resolve => {
      const proc = spawn(gitPath, ['rev-parse', 'HEAD'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', () => {
        resolve(output.trim())
      })
      proc.on('error', () => resolve(''))
    })

    if (currentCommitHash) {
      try {
        const shallowPath = path.join(repoPath, '.git', 'shallow')
        fs.writeFileSync(shallowPath, currentCommitHash + '\n')
        console.log('✅ 更新shallow文件，确保浅克隆状态')
      } catch (error) {
        console.log('⚠️ 更新shallow文件失败:', error)
      }
    }

    // 6. 执行激进的垃圾回收
    console.log('🧹 执行激进垃圾回收...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['gc', '--aggressive', '--prune=now'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => {
        console.log('✅ 激进垃圾回收完成')
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 7. 重新打包以最小化存储
    console.log('📦 重新打包以最小化存储...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['repack', '-a', '-d', '-f', '--depth=1', '--window=1'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => {
        console.log('✅ 仓库重新打包完成')
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 8. 显示优化效果
    await showStorageOptimizationResult(gitPath, gitEnv, repoPath)

    console.log('✅ 拉取后极致存储优化完成')
  } catch (error) {
    console.error('❌ 拉取后存储优化失败:', error)
  }
}

// 显示存储优化结果
async function showStorageOptimizationResult(
  gitPath: string,
  gitEnv: any,
  repoPath: string
): Promise<void> {
  console.log('=== 存储优化结果统计 ===')

  try {
    // 获取仓库大小
    const gitDirPath = path.join(repoPath, '.git')
    if (fs.existsSync(gitDirPath)) {
      const getDirectorySize = (dirPath: string): number => {
        let totalSize = 0
        try {
          const items = fs.readdirSync(dirPath)
          for (const item of items) {
            const itemPath = path.join(dirPath, item)
            const stats = fs.statSync(itemPath)
            if (stats.isDirectory()) {
              totalSize += getDirectorySize(itemPath)
            } else {
              totalSize += stats.size
            }
          }
        } catch (error) {
          // 忽略权限错误等
        }
        return totalSize
      }

      const gitDirSize = getDirectorySize(gitDirPath)
      const gitDirSizeMB = (gitDirSize / 1024 / 1024).toFixed(2)
      console.log(`📊 .git目录大小: ${gitDirSizeMB} MB`)
    }

    // 获取分支数量
    const branchCount = await new Promise<number>(resolve => {
      const proc = spawn(gitPath, ['branch', '-a'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', () => {
        const branches = output.split('\n').filter(line => line.trim())
        resolve(branches.length)
      })
      proc.on('error', () => resolve(0))
    })

    // 获取commit数量
    const commitCount = await new Promise<number>(resolve => {
      const proc = spawn(gitPath, ['rev-list', '--count', 'HEAD'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', () => {
        const count = parseInt(output.trim()) || 0
        resolve(count)
      })
      proc.on('error', () => resolve(0))
    })

    // 检查是否为浅克隆
    const isShallow = fs.existsSync(path.join(repoPath, '.git', 'shallow'))

    console.log(`📈 优化结果:`)
    console.log(`   - 分支数量: ${branchCount}`)
    console.log(`   - commit数量: ${commitCount}`)
    console.log(`   - 浅克隆状态: ${isShallow ? '✅ 是' : '❌ 否'}`)
    console.log(`   - 存储优化: ${commitCount === 1 ? '✅ 最优（仅保留最新commit）' : '⚠️ 可进一步优化'}`)

  } catch (error) {
    console.log('⚠️ 获取优化结果统计失败:', error)
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

  // 获取代理配置（同步版本）
  let proxyConfig: { httpProxy?: string; httpsProxy?: string } = {}
  try {
    const configPath = path.join(appRoot, 'config', 'Config.json')
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'))
      const proxyAddress = config?.Update?.ProxyAddress

      if (proxyAddress && proxyAddress.trim()) {
        let proxyUrl = proxyAddress.trim()

        // 自动添加协议前缀
        if (!proxyUrl.startsWith('http://') && !proxyUrl.startsWith('https://') && !proxyUrl.startsWith('socks5://')) {
          proxyUrl = `http://${proxyUrl}`
        }

        console.log(`✅ 检测到代理配置: ${proxyUrl}`)
        proxyConfig = {
          httpProxy: proxyUrl,
          httpsProxy: proxyUrl
        }
      }
    }
  } catch (error) {
    console.warn('读取代理配置失败:', error)
  }

  const env: { [key: string]: string | undefined } = {
    ...process.env,
    // 修复remote-https问题的关键：确保所有Git相关路径都在PATH中
    PATH: `${binPath};${mingw64BinPath};${gitCorePath};${process.env.PATH}`,
    GIT_EXEC_PATH: gitCorePath,
    GIT_TEMPLATE_DIR: path.join(gitDir, 'mingw64', 'share', 'git-core', 'templates'),
    HOME: process.env.USERPROFILE || process.env.HOME,
    // 禁用系统Git配置
    GIT_CONFIG_NOSYSTEM: '1',
    // 禁用交互式认证
    GIT_TERMINAL_PROMPT: '0',
    GIT_ASKPASS: '',
    // 确保Git能找到所有必要的程序
    GIT_HTTP_LOW_SPEED_LIMIT: '0',
    GIT_HTTP_LOW_SPEED_TIME: '0',
  }

  // 添加代理环境变量
  if (proxyConfig.httpProxy) {
    env.HTTP_PROXY = proxyConfig.httpProxy
    env.http_proxy = proxyConfig.httpProxy
    console.log(`✅ 设置Git HTTP代理: ${proxyConfig.httpProxy}`)
  }

  if (proxyConfig.httpsProxy) {
    env.HTTPS_PROXY = proxyConfig.httpsProxy
    env.https_proxy = proxyConfig.httpsProxy
    console.log(`✅ 设置Git HTTPS代理: ${proxyConfig.httpsProxy}`)
  }

  return env
}

// 检查是否为Git仓库
function isGitRepository(dirPath: string): boolean {
  const gitDir = path.join(dirPath, '.git')
  return fs.existsSync(gitDir)
}

// 检查Git仓库状态和完整性
async function checkGitRepositoryHealth(
  gitPath: string,
  gitEnv: any,
  repoPath: string
): Promise<{
  isHealthy: boolean
  issues: string[]
  currentBranch?: string
  workingTreeClean?: boolean
}> {
  console.log('=== 检查Git仓库健康状态 ===')
  const issues: string[] = []

  try {
    // 1. 检查当前分支
    const currentBranch = await new Promise<string>((resolve) => {
      const proc = spawn(gitPath, ['branch', '--show-current'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      let output = ''
      proc.stdout?.on('data', data => { output += data.toString() })
      proc.on('close', code => {
        if (code === 0) {
          resolve(output.trim())
        } else {
          issues.push('无法获取当前分支信息')
          resolve('')
        }
      })
      proc.on('error', () => {
        issues.push('获取当前分支时进程错误')
        resolve('')
      })
    })

    // 2. 检查工作树状态
    const workingTreeClean = await new Promise<boolean>((resolve) => {
      const proc = spawn(gitPath, ['status', '--porcelain'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      let output = ''
      proc.stdout?.on('data', data => { output += data.toString() })
      proc.on('close', code => {
        if (code === 0) {
          const isClean = output.trim() === ''
          if (!isClean) {
            issues.push(`工作树不干净，有未提交的更改: ${output.trim()}`)
          }
          resolve(isClean)
        } else {
          issues.push('无法检查工作树状态')
          resolve(false)
        }
      })
      proc.on('error', () => {
        issues.push('检查工作树状态时进程错误')
        resolve(false)
      })
    })

    // 3. 检查远程仓库连接
    const remoteAccessible = await new Promise<boolean>((resolve) => {
      const proc = spawn(gitPath, ['remote', 'show', 'origin'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', code => {
        if (code !== 0) {
          issues.push('无法访问远程仓库 origin')
        }
        resolve(code === 0)
      })
      proc.on('error', () => {
        issues.push('检查远程仓库时进程错误')
        resolve(false)
      })
    })

    // 4. 检查Git对象数据库完整性
    const objectDbHealthy = await new Promise<boolean>((resolve) => {
      const proc = spawn(gitPath, ['fsck', '--quick'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', code => {
        if (code !== 0) {
          issues.push('Git对象数据库存在问题，需要修复')
        }
        resolve(code === 0)
      })
      proc.on('error', () => {
        issues.push('检查Git对象数据库时进程错误')
        resolve(false)
      })
    })

    const isHealthy = issues.length === 0
    console.log(`Git仓库健康状态: ${isHealthy ? '✅ 健康' : '❌ 有问题'}`)
    if (issues.length > 0) {
      console.log('发现的问题:')
      issues.forEach(issue => console.log(`  - ${issue}`))
    }

    return {
      isHealthy,
      issues,
      currentBranch,
      workingTreeClean
    }
  } catch (error) {
    console.error('检查Git仓库健康状态时出错:', error)
    issues.push(`健康检查异常: ${error instanceof Error ? error.message : String(error)}`)
    return {
      isHealthy: false,
      issues
    }
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
// Git故障自动恢复函数
export async function autoRecoverFromGitFailure(
  appRoot: string,
  repoUrl: string = 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git'
): Promise<{ success: boolean; message: string }> {
  console.log('=== 开始Git故障自动恢复 ===')

  try {
    const repoPath = path.join(appRoot, 'repo')

    // 1. 清理损坏的仓库
    if (fs.existsSync(repoPath)) {
      console.log('🗑️ 清理可能损坏的仓库目录...')
      fs.rmSync(repoPath, { recursive: true, force: true })
      console.log('✅ 仓库目录清理完成')
    }

    // 2. 重新检查Git环境
    console.log('🔧 重新检查Git环境...')
    const gitEnv = getGitEnvironment(appRoot)
    const diagnosis = await diagnoseAndFixGitIssues(appRoot, gitEnv)

    if (!diagnosis.success) {
      return {
        success: false,
        message: `环境检查失败: ${diagnosis.error}`
      }
    }

    // 3. 使用配置的镜像源URL
    const actualRepoUrl = await getConfiguredRepoUrl(appRoot, repoUrl)
    console.log(`🔄 尝试重新克隆仓库: ${actualRepoUrl}`)
    const cloneResult = await cloneBackend(appRoot, actualRepoUrl)

    if (cloneResult.success) {
      return {
        success: true,
        message: '✅ Git故障自动恢复成功，仓库已重新克隆'
      }
    } else {
      return {
        success: false,
        message: `自动恢复失败: ${cloneResult.error}`
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    console.error('❌ 自动恢复过程出错:', errorMsg)
    return {
      success: false,
      message: `自动恢复异常: ${errorMsg}`
    }
  }
}

// 诊断和修复Git checkout问题
export async function diagnoseAndFixGitIssues(appRoot: string, gitEnv?: any): Promise<{
  success: boolean
  diagnostics: string[]
  fixes: string[]
  error?: string
}> {
  const diagnostics: string[] = []
  const fixes: string[] = []

  try {
    const repoPath = path.join(appRoot, 'repo')
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')

    diagnostics.push(`检查路径: ${repoPath}`)
    diagnostics.push(`Git可执行文件: ${gitPath}`)

    // 1. 检查基本文件存在性
    if (!fs.existsSync(gitPath)) {
      diagnostics.push('❌ Git可执行文件不存在')
      fixes.push('需要重新下载安装Git')
      return { success: false, diagnostics, fixes, error: 'Git可执行文件不存在' }
    }
    diagnostics.push('✅ Git可执行文件存在')

    if (!fs.existsSync(repoPath)) {
      diagnostics.push('❌ 仓库目录不存在')
      fixes.push('将重新克隆仓库')
      return { success: true, diagnostics, fixes }
    }
    diagnostics.push('✅ 仓库目录存在')

    // 使用传入的gitEnv或获取新的环境配置
    const actualGitEnv = gitEnv || getGitEnvironment(appRoot)

    // 2. 检查Git可用性
    const gitWorking = await new Promise<{ working: boolean; version?: string; error?: string }>((resolve) => {
      const proc = spawn(gitPath, ['--version'], { env: actualGitEnv, stdio: 'pipe' })
      let output = ''
      let error = ''

      proc.stdout?.on('data', data => { output += data.toString() })
      proc.stderr?.on('data', data => { error += data.toString() })

      proc.on('close', code => {
        resolve({
          working: code === 0,
          version: output.trim(),
          error: error.trim()
        })
      })
      proc.on('error', err => {
        resolve({ working: false, error: err.message })
      })
    })

    if (!gitWorking.working) {
      diagnostics.push(`❌ Git无法运行: ${gitWorking.error}`)
      fixes.push('检查Git安装完整性，可能需要重新安装Git')
      return { success: false, diagnostics, fixes, error: gitWorking.error }
    }
    diagnostics.push(`✅ Git正常工作: ${gitWorking.version}`)

    // 3. 检查仓库状态
    if (fs.existsSync(path.join(repoPath, '.git'))) {
      diagnostics.push('✅ 是Git仓库')

      // 运行健康检查
      const healthCheck = await checkGitRepositoryHealth(gitPath, actualGitEnv, repoPath)
      if (!healthCheck.isHealthy) {
        diagnostics.push('❌ Git仓库健康检查失败')
        healthCheck.issues.forEach(issue => diagnostics.push(`  - ${issue}`))
        fixes.push('将清理并重新克隆仓库')
      } else {
        diagnostics.push('✅ Git仓库健康状态良好')
      }
    } else {
      diagnostics.push('❌ 不是Git仓库')
      fixes.push('将重新克隆仓库')
    }

    return { success: true, diagnostics, fixes }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    diagnostics.push(`❌ 诊断过程出错: ${errorMsg}`)
    return { success: false, diagnostics, fixes, error: errorMsg }
  }
}

// 优化前端配置，自动选择最佳镜像源
export async function optimizeFrontendGitConfig(appRoot: string): Promise<{
  success: boolean
  oldMirror?: string
  newMirror?: string
  message: string
}> {
  try {
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (!fs.existsSync(configPath)) {
      return { success: false, message: '前端配置文件不存在' }
    }

    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'))
    const currentMirror = config.selectedGitMirror || 'github'

    // 如果已经是推荐的镜像源，则无需优化
    if (currentMirror !== 'github') {
      return {
        success: true,
        oldMirror: currentMirror,
        newMirror: currentMirror,
        message: `当前已使用加速镜像源: ${currentMirror}`
      }
    }

    // 选择最佳镜像源
    const bestMirror = selectBestMirror()

    // 更新配置
    config.selectedGitMirror = bestMirror.key
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8')

    console.log(`✅ 已自动优化Git镜像源配置: ${currentMirror} -> ${bestMirror.key}`)
    console.log(`优化理由: ${bestMirror.reason}`)

    return {
      success: true,
      oldMirror: currentMirror,
      newMirror: bestMirror.key,
      message: `已自动优化为 ${bestMirror.key}，${bestMirror.reason}`
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    console.error('优化前端Git配置失败:', errorMsg)
    return { success: false, message: `优化失败: ${errorMsg}` }
  }
}

// 验证镜像站配置是否真正生效的测试函数
export async function verifyMirrorConfiguration(appRoot: string): Promise<{
  success: boolean
  currentMirror: string
  effectiveUrl: string
  isUsingAccelerator: boolean
  details: string[]
}> {
  const details: string[] = []

  try {
    // 1. 检查前端配置
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')
    if (!fs.existsSync(configPath)) {
      return {
        success: false,
        currentMirror: 'unknown',
        effectiveUrl: '',
        isUsingAccelerator: false,
        details: ['前端配置文件不存在']
      }
    }

    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'))
    const selectedMirror = config.selectedGitMirror || 'github'
    details.push(`前端配置的镜像源: ${selectedMirror}`)

    // 2. 获取实际生效的仓库URL
    const effectiveUrl = await getConfiguredRepoUrl(appRoot, 'main')
    details.push(`实际生效的仓库URL: ${effectiveUrl}`)

    // 3. 判断是否使用了加速站
    const isUsingAccelerator = !effectiveUrl.includes('github.com') ||
      effectiveUrl.includes('gh-proxy.com') ||
      effectiveUrl.includes('ghproxy') ||
      effectiveUrl.includes('gitee.com') ||
      effectiveUrl.includes('ghfast.top')
    details.push(`是否使用加速站: ${isUsingAccelerator ? '是' : '否'}`)

    // 4. 如果没有使用加速站但配置了非GitHub镜像，说明配置可能有问题
    if (!isUsingAccelerator && selectedMirror !== 'github') {
      details.push(`⚠️  配置了镜像源${selectedMirror}但实际仍使用GitHub，配置可能未生效`)
    }

    // 5. 检查环境变量
    const gitEnv = getGitEnvironment(appRoot)
    if (gitEnv.https_proxy) {
      details.push(`Git代理设置: ${gitEnv.https_proxy}`)
    }

    return {
      success: true,
      currentMirror: selectedMirror,
      effectiveUrl,
      isUsingAccelerator,
      details
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    return {
      success: false,
      currentMirror: 'unknown',
      effectiveUrl: '',
      isUsingAccelerator: false,
      details: [`验证失败: ${errorMsg}`]
    }
  }
}

// 为前端提供的综合Git状态和故障排除接口
export async function getGitStatusAndTroubleshoot(appRoot: string): Promise<{
  success: boolean
  repoInfo?: {
    repoExists: boolean
    isGitRepo: boolean
    currentBranch?: string
    currentCommit?: string
    remoteUrl?: string
    lastUpdate?: string
  }
  diagnostics?: string[]
  fixes?: string[]
  canAutoRecover?: boolean
  error?: string
}> {
  try {
    console.log('=== 获取Git状态并进行故障排除 ===')

    // 1. 获取基本仓库信息
    const repoInfo = await getRepoInfo(appRoot)

    // 2. 运行诊断
    const gitEnv = getGitEnvironment(appRoot)
    const diagnosis = await diagnoseAndFixGitIssues(appRoot, gitEnv)

    // 3. 判断是否可以自动恢复
    const canAutoRecover = !diagnosis.success || diagnosis.fixes.length > 0

    return {
      success: true,
      repoInfo: repoInfo.info,
      diagnostics: diagnosis.diagnostics,
      fixes: diagnosis.fixes,
      canAutoRecover,
      error: diagnosis.error
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    console.error('获取Git状态和故障排除失败:', errorMsg)
    return {
      success: false,
      error: errorMsg
    }
  }
}

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
        message: '开始多线程下载Git...',
      })
    }

    // 智能下载Git压缩包，自动选择最佳下载方式
    const zipPath = path.join(environmentPath, 'git.zip')
    await downloadWithFallback(gitDownloadUrl, zipPath, 6, {
      type: 'git',
      message: '回退到单线程下载Git...'
    })

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

// 快速安装：下载预打包源码
export async function downloadQuickSource(appRoot: string): Promise<{ success: boolean; error?: string }> {
  try {
    const sourceUrl = 'https://download.auto-mas.top/d/AUTO-MAS/repo.zip'
    const downloadPath = path.join(appRoot, 'temp', 'repo.zip')

    // 确保临时目录存在
    const tempDir = path.dirname(downloadPath)
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true })
    }

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 2,
        progress: 50,
        status: 'downloading',
        message: '开始多线程下载源码包...',
      })
    }

    // 智能下载源码包，自动选择最佳下载方式
    await downloadWithFallback(sourceUrl, downloadPath, 8, {
      step: 2,
      message: '回退到单线程下载源码包...'
    })

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 2,
        progress: 60,
        status: 'completed',
        message: '源码包下载完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMsg = `源码包下载失败: ${error instanceof Error ? error.message : String(error)}`
    console.error(errorMsg)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 2,
        progress: 0,
        status: 'error',
        message: errorMsg,
      })
    }
    return { success: false, error: errorMsg }
  }
}

// 快速安装：解压预打包源码
export async function extractQuickSource(appRoot: string): Promise<{ success: boolean; error?: string }> {
  try {
    const zipPath = path.join(appRoot, 'temp', 'repo.zip')
    const tempExtractPath = path.join(appRoot, 'temp', 'repo')

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 3,
        progress: 70,
        status: 'extracting',
        message: '开始解压源码包...',
      })
    }

    if (!fs.existsSync(zipPath)) {
      throw new Error('源码包文件不存在')
    }

    // 先解压到临时目录
    const AdmZip = (await import('adm-zip')).default
    const zip = new AdmZip(zipPath)
    zip.extractAllTo(tempExtractPath, true)

    // 查找解压后的实际目录（可能包含版本号等）
    const extractedItems = fs.readdirSync(tempExtractPath)
    let sourceDir = tempExtractPath

    // 如果解压后只有一个目录，进入该目录
    if (extractedItems.length === 1) {
      const itemPath = path.join(tempExtractPath, extractedItems[0])
      if (fs.statSync(itemPath).isDirectory()) {
        sourceDir = itemPath
      }
    }

    // 复制文件到应用根目录，但跳过已存在的关键文件
    await copySourceFiles(sourceDir, appRoot)

    // 清理临时文件
    fs.unlinkSync(zipPath)
    if (fs.existsSync(tempExtractPath)) {
      fs.rmSync(tempExtractPath, { recursive: true, force: true })
    }

    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 3,
        progress: 80,
        status: 'completed',
        message: '源码包解压完成',
      })
    }

    return { success: true }
  } catch (error) {
    const errorMsg = `源码包解压失败: ${error instanceof Error ? error.message : String(error)}`
    console.error(errorMsg)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 3,
        progress: 0,
        status: 'error',
        message: errorMsg,
      })
    }
    return { success: false, error: errorMsg }
  }
}

// 快速安装：更新源码到最新版本
export async function updateQuickSource(appRoot: string, repoUrl?: string): Promise<{ success: boolean; error?: string }> {
  try {
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 4,
        progress: 85,
        status: 'updating',
        message: '正在更新到最新代码...',
      })
    }

    // 使用现有的cloneBackend函数，它会自动判断是pull还是clone
    const result = await cloneBackend(appRoot, repoUrl)

    if (result.success) {
      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          step: 4,
          progress: 90,
          status: 'completed',
          message: '代码更新完成',
        })
      }
      return { success: true }
    } else {
      // 如果更新失败，不要抛出错误，只是记录警告
      console.warn('代码更新失败，但继续安装流程:', result.error)
      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          step: 4,
          progress: 90,
          status: 'warning',
          message: '代码更新失败，使用下载的版本继续',
        })
      }
      return { success: true } // 返回成功，继续后续流程
    }
  } catch (error) {
    // 更新失败不影响整体流程
    console.warn('代码更新异常，但继续安装流程:', error)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', {
        step: 4,
        progress: 90,
        status: 'warning',
        message: '代码更新失败，使用下载的版本继续',
      })
    }
    return { success: true }
  }
}

// 复制源码文件，跳过已存在的关键文件
async function copySourceFiles(sourceDir: string, targetDir: string) {
  const skipFiles = [
    'frontend', // 跳过前端目录，避免覆盖当前运行的前端
    'node_modules',
    '.git',
    'temp',
    'debug',
    'data',
    'history',
    'config', // 跳过配置目录，保留用户配置
  ]

  const items = fs.readdirSync(sourceDir)

  for (const item of items) {
    if (skipFiles.includes(item)) {
      console.log(`跳过文件/目录: ${item}`)
      continue
    }

    const sourcePath = path.join(sourceDir, item)
    const targetPath = path.join(targetDir, item)

    if (fs.statSync(sourcePath).isDirectory()) {
      // 递归复制目录
      if (!fs.existsSync(targetPath)) {
        fs.mkdirSync(targetPath, { recursive: true })
      }
      await copyDirectoryRecursive(sourcePath, targetPath)
    } else {
      // 复制文件
      fs.copyFileSync(sourcePath, targetPath)
    }
  }
}

// 递归复制目录
async function copyDirectoryRecursive(sourceDir: string, targetDir: string) {
  const items = fs.readdirSync(sourceDir)

  for (const item of items) {
    const sourcePath = path.join(sourceDir, item)
    const targetPath = path.join(targetDir, item)

    if (fs.statSync(sourcePath).isDirectory()) {
      if (!fs.existsSync(targetPath)) {
        fs.mkdirSync(targetPath, { recursive: true })
      }
      await copyDirectoryRecursive(sourcePath, targetPath)
    } else {
      fs.copyFileSync(sourcePath, targetPath)
    }
  }
}

// Git镜像源配置映射（与云端配置保持同步）
const GIT_MIRROR_URLS = {
  // 官方源
  'github': 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git',

  // 国内镜像源
  'gitee': 'https://gitee.com/auto-mas-project/AUTO-MAS.git',
  'gitee 镜像源': 'https://gitee.com/auto-mas-project/AUTO-MAS.git',

  // GitHub加速站（gh-proxy系列）
  'ghproxy_cloudflare': 'https://gh-proxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
  'ghproxy_fastly': 'https://cdn.gh-proxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
  'ghproxy_edgeone': 'https://edgeone.gh-proxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',

  // 第三方加速站
  'ghfast': 'https://ghfast.top/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',

  // 兼容老配置
  'ghproxy_net': 'https://ghproxy.net/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
  'hub_fastgit': 'https://hub.fastgit.xyz/AUTO-MAS-Project/AUTO-MAS.git',
} as const

// 智能选择最佳镜像源
function selectBestMirror(): { key: string; url: string; reason: string } {
  // 中国大陆用户推荐的加速站优先级（从高到低）
  const recommendedMirrors = [
    { key: 'gitee', reason: '国内gitee镜像，稳定性好' },
    { key: 'ghproxy_cloudflare', reason: 'Cloudflare CDN加速，全球覆盖' },
    { key: 'ghproxy_fastly', reason: 'Fastly CDN加速，速度快' },
    { key: 'ghproxy_edgeone', reason: 'EdgeOne加速，腾讯云CDN' },
    { key: 'ghfast', reason: '第三方GitHub加速站' },
  ]

  // 选择第一个可用的镜像
  for (const mirror of recommendedMirrors) {
    const url = GIT_MIRROR_URLS[mirror.key as keyof typeof GIT_MIRROR_URLS]
    if (url) {
      return { key: mirror.key, url, reason: mirror.reason }
    }
  }

  // 如果都不可用，回退到GitHub官方
  return {
    key: 'github',
    url: GIT_MIRROR_URLS.github,
    reason: 'GitHub官方源（可能需要科学上网）'
  }
}

// 获取配置的Git仓库URL
async function getConfiguredRepoUrl(appRoot: string, defaultUrl: string): Promise<string> {
  console.log(`=== Git镜像源配置 ===`)

  try {
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'))
      let selectedMirror = config.selectedGitMirror || 'github'

      console.log(`配置中的镜像源: ${selectedMirror}`)

      // 如果配置的是GitHub官方源，建议自动切换到加速站
      if (selectedMirror === 'github') {
        const bestMirror = selectBestMirror()
        console.log(`⚡ 检测到GitHub官方源，推荐使用加速站: ${bestMirror.key}`)
        console.log(`推荐理由: ${bestMirror.reason}`)

        // 可以选择是否强制切换到加速站
        // 这里暂时保持用户配置，但给出建议
        console.log(`💡 建议: 可在前端界面切换到 ${bestMirror.key} 以获得更好的下载速度`)
      }

      // 从映射表中获取对应的URL
      const mirrorUrl = GIT_MIRROR_URLS[selectedMirror as keyof typeof GIT_MIRROR_URLS]

      if (mirrorUrl) {
        console.log(`✅ 使用配置的镜像源: ${selectedMirror} -> ${mirrorUrl}`)
        return mirrorUrl
      } else {
        console.warn(`⚠️ 未知的镜像源配置: ${selectedMirror}`)

        // 检查是否为自定义URL（包含http或https）
        if (selectedMirror.includes('http://') || selectedMirror.includes('https://')) {
          console.log(`✅ 使用自定义镜像源URL: ${selectedMirror}`)
          return selectedMirror
        }

        // 如果配置的镜像源无效，自动选择最佳镜像
        console.log(`🔄 配置无效，自动选择最佳镜像源...`)
        const bestMirror = selectBestMirror()
        console.log(`✅ 自动选择: ${bestMirror.key} -> ${bestMirror.url}`)
        console.log(`选择原因: ${bestMirror.reason}`)
        return bestMirror.url
      }
    } else {
      console.log('前端配置文件不存在，自动选择最佳镜像源')
      const bestMirror = selectBestMirror()
      console.log(`✅ 自动选择: ${bestMirror.key} -> ${bestMirror.url}`)
      console.log(`选择原因: ${bestMirror.reason}`)
      return bestMirror.url
    }
  } catch (error) {
    console.warn('读取Git镜像源配置失败，自动选择最佳镜像源:', error)
    const bestMirror = selectBestMirror()
    console.log(`✅ 异常恢复选择: ${bestMirror.key} -> ${bestMirror.url}`)
    return bestMirror.url
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
  console.log(`默认仓库URL: ${repoUrl}`)
  console.log('📋 执行顺序：1.镜像站配置 → 2.环境配置 → 3.诊断 → 4.分支选择 → 5.Git操作')

  try {
    // 🎯 第一步：立即配置镜像站和加速站，确保在所有检查之前完成
    console.log('=== 第一步：配置镜像站和加速站 ===')
    const actualRepoUrl = await getConfiguredRepoUrl(appRoot, repoUrl)
    console.log(`✅ 镜像站配置完成，实际使用的仓库URL: ${actualRepoUrl}`)

    // 验证是否使用了加速站
    const isUsingAccelerator = !actualRepoUrl.includes('github.com') ||
      actualRepoUrl.includes('gh-proxy.com') ||
      actualRepoUrl.includes('ghproxy') ||
      actualRepoUrl.includes('gitee.com') ||
      actualRepoUrl.includes('ghfast.top')

    if (isUsingAccelerator) {
      console.log(`🚀 已启用加速站，预计下载速度将显著提升`)
    } else {
      console.log(`⚠️ 当前使用GitHub官方源，如遇网络问题建议切换到镜像加速站`)
    }

    // 更新repoUrl变量为实际配置的URL，后续所有操作都使用这个URL
    repoUrl = actualRepoUrl

    // 🔧 第二步：预配置Git环境（包括代理设置）
    console.log('=== 第二步：预配置Git环境和代理 ===')
    const repoPath = path.join(appRoot, 'repo')
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
    const gitEnv = getGitEnvironment(appRoot) // 这里会配置代理环境变量

    console.log(`✅ Git环境配置完成`)
    console.log(`Git可执行文件路径: ${gitPath}`)
    console.log(`仓库路径: ${repoPath}`)
    console.log(`使用仓库URL: ${repoUrl}`)

    // 🔍 第三步：环境和仓库诊断
    console.log('=== 第三步：运行环境诊断 ===')
    const diagnosis = await diagnoseAndFixGitIssues(appRoot, gitEnv)

    console.log('📋 诊断结果:')
    diagnosis.diagnostics.forEach(item => console.log(`  ${item}`))

    if (diagnosis.fixes.length > 0) {
      console.log('🔧 建议修复:')
      diagnosis.fixes.forEach(fix => console.log(`  ${fix}`))
    }

    if (!diagnosis.success) {
      throw new Error(`环境诊断失败: ${diagnosis.error}`)
    }

    if (!fs.existsSync(gitPath)) {
      const error = `Git可执行文件不存在: ${gitPath}`
      console.error(`❌ ${error}`)
      throw new Error(error)
    }

    console.log('✅ Git可执行文件存在')
    console.log('✅ Git环境变量配置完成（已在第二步配置）')

    // 检查 git 是否可用
    console.log('=== 检查Git是否可用 ===')
    console.log(`Git可执行文件: ${gitPath}`)
    console.log(`Git PATH环境: ${gitEnv.PATH?.split(';')[0]}`)
    console.log(`Git GIT_EXEC_PATH: ${gitEnv.GIT_EXEC_PATH}`)

    await new Promise<void>((resolve, reject) => {
      const proc = spawn(gitPath, ['--version'], {
        env: gitEnv,
        stdio: 'pipe'
      })

      let versionOutput = ''
      let errorOutput = ''

      proc.stdout?.on('data', data => {
        const output = data.toString().trim()
        versionOutput += output
        console.log(`git --version output: ${output}`)
      })

      proc.stderr?.on('data', data => {
        const output = data.toString().trim()
        errorOutput += output
        console.log(`git --version error: ${output}`)
      })

      proc.on('close', code => {
        console.log(`git --version 退出码: ${code}`)
        if (code === 0) {
          console.log(`✅ Git可用，版本: ${versionOutput}`)
          resolve()
        } else {
          console.error('❌ Git无法正常运行')
          const error = errorOutput || '未知错误'
          reject(new Error(`Git无法正常运行，退出码: ${code}，错误: ${error}`))
        }
      })

      proc.on('error', error => {
        console.error('❌ Git进程启动失败:', error)
        console.error('可能的原因:')
        console.error('  1. Git可执行文件不存在或损坏')
        console.error('  2. 缺少必要的DLL文件')
        console.error('  3. 权限不足')
        console.error('  4. 环境变量配置错误')
        reject(new Error(`Git进程启动失败: ${error.message}`))
      })
    })

    // 获取版本号并确定目标分支
    const version = getAppVersion(appRoot)
    console.log(`=== 分支选择逻辑 ===`)
    console.log(`当前应用版本: ${version}`)

    let targetBranch = DEFAULT_BRANCH // 使用常量定义的默认分支
    console.log(`默认分支: ${targetBranch}`)

    // 分支选择策略：优先版本分支，其次默认分支，最后fallback到main
    console.log('=== 开始智能分支选择 ===')

    let selectedBranch = null
    let selectionReason = ''

    // 1. 优先测试版本号分支（如果版本号有效）
    if (version !== '获取版本失败！') {
      console.log(`🎯 第一优先级：检查版本分支 ${version}`)
      const versionBranchExists = await checkBranchExists(gitPath, gitEnv, repoUrl, version)
      if (versionBranchExists) {
        selectedBranch = version
        selectionReason = `版本分支 ${version} 存在且可访问`
        console.log(`✅ ${selectionReason}`)
      } else {
        console.log(`❌ 版本分支 ${version} 不存在`)
      }
    } else {
      console.log('⚠️ 版本号获取失败，跳过版本分支检测')
    }

    // 2. 如果版本分支不可用，测试默认分支
    if (!selectedBranch) {
      console.log(`🔄 第二优先级：检查默认分支 ${targetBranch}`)
      const defaultBranchExists = await checkBranchExists(gitPath, gitEnv, repoUrl, targetBranch)
      if (defaultBranchExists) {
        selectedBranch = targetBranch
        selectionReason = `默认分支 ${targetBranch} 存在且可访问`
        console.log(`✅ ${selectionReason}`)
      } else {
        console.log(`❌ 默认分支 ${targetBranch} 不存在`)
      }
    }

    // 3. 最后的fallback：尝试main分支
    if (!selectedBranch) {
      console.log(`🆘 最后选择：尝试 main 分支作为fallback`)
      const mainBranchExists = await checkBranchExists(gitPath, gitEnv, repoUrl, 'main')
      if (mainBranchExists) {
        selectedBranch = 'main'
        selectionReason = 'fallback到main分支'
        console.log(`✅ ${selectionReason}`)
      } else {
        console.log(`❌ main 分支也不存在`)
        throw new Error('网络连接不可用或无法访问远程仓库，所有候选分支都不可用，请检查网络连接后重试')
      }
    }

    targetBranch = selectedBranch
    console.log('✅ 网络连接正常，可以访问远程仓库')

    console.log(`=== 最终选择分支: ${targetBranch} ===`)
    console.log(`选择原因: ${selectionReason}`)

    // 检查是否为Git仓库
    const isRepo = isGitRepository(repoPath)
    console.log(`检查是否为Git仓库: ${isRepo ? '✅ 是' : '❌ 否'}`)

    // ==== 下面是关键逻辑 ====
    if (isRepo) {
      console.log('=== 更新现有Git仓库 ===')

      // 首先检查Git仓库健康状态
      const healthCheck = await checkGitRepositoryHealth(gitPath, gitEnv, repoPath)
      if (!healthCheck.isHealthy) {
        console.warn('⚠️ Git仓库存在问题，启动自动恢复流程')
        console.log('发现的问题:')
        healthCheck.issues.forEach(issue => console.log(`  - ${issue}`))

        // 尝试自动恢复
        console.log('� 启动Git故障自动恢复...')
        const recoveryResult = await autoRecoverFromGitFailure(appRoot, repoUrl)

        if (recoveryResult.success) {
          console.log(`✅ ${recoveryResult.message}`)
          return { success: true }
        } else {
          console.error(`❌ ${recoveryResult.message}`)
          throw new Error(recoveryResult.message)
        }
      }

      console.log('✅ Git仓库健康状态良好，继续更新流程')

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: `正在更新后端代码(分支: ${targetBranch})...`,
        })
      }

      // 1. 优化配置：只拉取目标分支的最新 commit
      console.log(`🔧 优化配置git仓库，只拉取目标分支: ${targetBranch}`)

      // 清理现有的fetch配置
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
          resolve()
        })
        proc.on('error', error => {
          console.log('⚠️ git config --unset-all 进程错误，但继续执行:', error)
          resolve()
        })
      })

      // 设置只拉取目标分支的配置
      await configureShallowRepository(gitPath, gitEnv, repoPath, targetBranch)

      // 2. 极致优化拉取：只获取目标分支的最新 commit（depth=1，无历史）
      console.log(`📥 极致优化拉取目标分支最新 commit: ${targetBranch}`)

      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, [
          'fetch',
          'origin',
          targetBranch,
          '--depth=1',           // 只拉取最新commit
          '--no-tags',           // 不拉取标签
          '--force',             // 强制更新
          '--prune',             // 清理远程已删除的分支
          '--prune-tags',        // 清理远程已删除的标签
          '--update-shallow'     // 更新浅克隆
        ], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })

        let errorOutput = ''
        proc.stdout?.on('data', d =>
          console.log(`git fetch ${targetBranch} stdout:`, d.toString().trim())
        )
        proc.stderr?.on('data', d => {
          const stderr = d.toString().trim()
          console.log(`git fetch ${targetBranch} stderr:`, stderr)
          errorOutput += stderr
        })

        proc.on('close', code => {
          console.log(`git fetch ${targetBranch} 退出码: ${code}`)
          if (code === 0) {
            console.log(`✅ 成功获取分支最新 commit: ${targetBranch}`)
            resolve()
          } else {
            console.error(`❌ 获取分支 ${targetBranch} 失败`)
            const isNetworkError = errorOutput.includes('unable to access') ||
              errorOutput.includes('Could not resolve host') ||
              errorOutput.includes('Connection refused') ||
              errorOutput.includes('network is unreachable')

            // Git fetch 失败时进行快速诊断
            console.log('=== Git fetch 失败，进行快速诊断 ===')
            diagnoseAndFixGitIssues(appRoot).then((fetchDiagnosis) => {
              console.log('🔍 Fetch失败诊断:')
              fetchDiagnosis.diagnostics.forEach(item => console.log(`  ${item}`))
            }).catch(diagError => {
              console.error('诊断过程出错:', diagError)
            })

            if (isNetworkError) {
              reject(new Error(`网络连接失败: 无法获取分支 ${targetBranch}`))
            } else {
              reject(new Error(`获取分支 ${targetBranch} 失败: ${errorOutput}`))
            }
          }
        })

        proc.on('error', error => {
          console.error(`❌ git fetch ${targetBranch} 进程错误:`, error)
          reject(error)
        })
      })

      console.log(`✅ 目标分支最新 commit 获取完成`)

      // 3. 强制切换到目标分支并设置远程跟踪
      console.log(`🔀 强制切换到目标分支: ${targetBranch}`)

      // 先检查远程分支是否存在
      console.log(`🔍 检查远程分支是否存在: origin/${targetBranch}`)
      const remoteBranchExists = await new Promise<boolean>((resolve) => {
        const proc = spawn(gitPath, ['branch', '-r', '--list', `origin/${targetBranch}`], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        let output = ''
        proc.stdout?.on('data', data => {
          output += data.toString()
        })
        proc.on('close', code => {
          const exists = output.trim().includes(`origin/${targetBranch}`)
          console.log(`远程分支 origin/${targetBranch} ${exists ? '存在' : '不存在'}`)
          resolve(exists)
        })
        proc.on('error', () => resolve(false))
      })

      if (!remoteBranchExists) {
        console.error(`❌ 远程分支 origin/${targetBranch} 不存在，无法切换`)
        throw new Error(`远程分支 origin/${targetBranch} 不存在`)
      }

      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['checkout', '-B', targetBranch, `origin/${targetBranch}`], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })

        let stdoutOutput = ''
        let stderrOutput = ''

        proc.stdout?.on('data', d => {
          const output = d.toString().trim()
          stdoutOutput += output
          console.log('git checkout stdout:', output)
        })

        proc.stderr?.on('data', d => {
          const output = d.toString().trim()
          stderrOutput += output
          console.log('git checkout stderr:', output)
        })

        proc.on('close', code => {
          console.log(`git checkout 退出码: ${code}`)
          console.log(`git checkout 完整输出:`)
          console.log(`  stdout: ${stdoutOutput}`)
          console.log(`  stderr: ${stderrOutput}`)

          if (code === 0) {
            console.log(`✅ 成功切换到分支: ${targetBranch}`)
            resolve()
          } else {
            console.error(`❌ 切换分支失败: ${targetBranch}`)
            const errorDetails = stderrOutput || stdoutOutput || '无详细错误信息'

            // Git checkout 失败时进行详细诊断
            console.log('=== Git checkout 失败，开始详细诊断 ===')
            diagnoseAndFixGitIssues(appRoot).then((failureDiagnosis) => {
              console.log('🔍 失败后诊断结果:')
              failureDiagnosis.diagnostics.forEach(item => console.log(`  ${item}`))

              if (failureDiagnosis.fixes.length > 0) {
                console.log('💡 建议的修复措施:')
                failureDiagnosis.fixes.forEach(fix => console.log(`  ${fix}`))
              }
            }).catch(diagError => {
              console.error('诊断过程也出错了:', diagError)
            })

            reject(new Error(`Git checkout失败，退出码: ${code}，错误详情: ${errorDetails}`))
          }
        })

        proc.on('error', error => {
          console.error('❌ git checkout 进程错误:', error)
          reject(new Error(`Git checkout进程启动失败: ${error.message}`))
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

      // 6. 拉取后极致存储优化：删除其他分支和历史 commit
      console.log('🧹 拉取后极致存储优化：删除其他分支和历史 commit...')
      await optimizePostPullStorage(gitPath, gitEnv, repoPath, targetBranch)

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

      console.log(`📥 开始优化克隆代码到仓库目录...`)
      console.log(`优化克隆参数: --single-branch --depth=1 --branch ${targetBranch} (只克隆目标分支最新 commit)`)

      await new Promise<void>((resolve, reject) => {
        const proc = spawn(
          gitPath,
          [
            'clone',
            '--progress',
            '--verbose',
            '--single-branch',
            '--depth=1',
            '--shallow-submodules',
            '--no-tags',
            '--filter=blob:none',  // 只拉取树对象，不拉取blob对象（进一步减少存储）
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
            console.log('✅ 优化克隆成功：只包含最新 commit，无历史记录')
            resolve()
          } else {
            console.error('❌ 优化克隆失败')
            const isNetworkError = errorOutput.includes('unable to access') ||
              errorOutput.includes('Could not resolve host') ||
              errorOutput.includes('Connection refused') ||
              errorOutput.includes('network is unreachable')

            // Git clone 失败时进行诊断
            console.log('=== Git clone 失败，进行环境诊断 ===')
            diagnoseAndFixGitIssues(appRoot).then((cloneDiagnosis) => {
              console.log('🔍 Clone失败诊断:')
              cloneDiagnosis.diagnostics.forEach(item => console.log(`  ${item}`))

              if (cloneDiagnosis.fixes.length > 0) {
                console.log('💡 针对克隆失败的建议:')
                cloneDiagnosis.fixes.forEach(fix => console.log(`  ${fix}`))
              }
            }).catch(diagError => {
              console.error('诊断过程出错:', diagError)
            })

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

      // 克隆后进一步优化：确保只保留目标分支
      console.log(`🔧 克隆后优化：确保只保留目标分支 ${targetBranch}`)

      // 配置浅克隆仓库
      await configureShallowRepository(gitPath, gitEnv, repoPath, targetBranch)

      // 2. 克隆后极致存储优化：删除其他分支和历史 commit
      console.log('🧹 克隆后极致存储优化：删除其他分支和历史 commit...')
      await optimizePostPullStorage(gitPath, gitEnv, repoPath, targetBranch)

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

// 完整的镜像站配置检查和优化流程
export async function checkAndOptimizeMirrorConfiguration(appRoot: string): Promise<{
  success: boolean
  actions: string[]
  finalStatus: {
    mirror: string
    url: string
    isAccelerated: boolean
  }
  message: string
}> {
  const actions: string[] = []

  try {
    // 1. 先验证当前配置状态
    actions.push('🔍 检查当前镜像站配置状态...')
    const verification = await verifyMirrorConfiguration(appRoot)

    actions.push(`当前镜像源: ${verification.currentMirror}`)
    actions.push(`实际URL: ${verification.effectiveUrl}`)
    actions.push(`使用加速站: ${verification.isUsingAccelerator ? '是' : '否'}`)

    // 2. 如果没有使用加速站，尝试优化配置
    if (!verification.isUsingAccelerator) {
      actions.push('⚡ 检测到未使用加速站，开始优化配置...')

      const optimization = await optimizeFrontendGitConfig(appRoot)
      if (optimization.success) {
        actions.push(`✅ ${optimization.message}`)

        // 3. 重新验证优化后的配置
        actions.push('🔄 验证优化后的配置...')
        const newVerification = await verifyMirrorConfiguration(appRoot)

        return {
          success: true,
          actions,
          finalStatus: {
            mirror: newVerification.currentMirror,
            url: newVerification.effectiveUrl,
            isAccelerated: newVerification.isUsingAccelerator
          },
          message: newVerification.isUsingAccelerator
            ? '✅ 镜像站配置已优化并正确生效'
            : '⚠️ 配置已优化但可能需要重启应用生效'
        }
      } else {
        actions.push(`❌ 优化失败: ${optimization.message}`)
      }
    } else {
      actions.push('✅ 当前已正确使用加速站，无需优化')
    }

    return {
      success: true,
      actions,
      finalStatus: {
        mirror: verification.currentMirror,
        url: verification.effectiveUrl,
        isAccelerated: verification.isUsingAccelerator
      },
      message: verification.isUsingAccelerator
        ? '当前镜像站配置正常'
        : '建议重启应用以确保配置生效'
    }

  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    actions.push(`❌ 检查过程出错: ${errorMsg}`)

    return {
      success: false,
      actions,
      finalStatus: {
        mirror: 'unknown',
        url: '',
        isAccelerated: false
      },
      message: `检查失败: ${errorMsg}`
    }
  }
}
