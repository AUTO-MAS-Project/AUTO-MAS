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

// 优化的分支和历史清理函数 - 极致存储优化版本
async function cleanOldLocalBranches(
  gitPath: string,
  gitEnv: any,
  repoPath: string,
  currentBranch: string,
  defaultBranch: string
): Promise<void> {
  console.log('=== 开始极致存储优化清理 ===')
  console.log(`当前分支: ${currentBranch}`)
  console.log(`目标: 只保留当前分支的最新commit，删除所有历史数据`)

  try {
    // 1. 删除所有远程分支引用（除了当前分支）
    console.log('🗑️ 清理所有远程分支引用...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['remote', 'prune', 'origin'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => resolve())
      proc.on('error', () => resolve())
    })

    // 2. 删除所有本地分支（除了当前分支）
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
            .filter(line => line && line !== currentBranch)
          console.log(`发现需要删除的分支: ${branches.join(', ')}`)
          resolve(branches)
        } else {
          resolve([])
        }
      })
      proc.on('error', () => resolve([]))
    })

    // 删除所有其他分支
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
          console.log(`发现标签: ${tagList.join(', ')}`)
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

    // 4. 创建孤立分支，彻底删除历史记录
    console.log('🔄 创建孤立分支，彻底删除历史记录...')

    // 获取当前HEAD的内容
    const currentCommitMessage = await new Promise<string>(resolve => {
      const proc = spawn(gitPath, ['log', '-1', '--pretty=format:%s'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', () => {
        resolve(output.trim() || 'Latest optimized commit')
      })
      proc.on('error', () => resolve('Latest optimized commit'))
    })

    // 创建孤立分支
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['checkout', '--orphan', 'temp-optimized'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => {
        console.log('✅ 孤立分支创建完成')
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 添加所有文件到新分支
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['add', '-A'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => resolve())
      proc.on('error', () => resolve())
    })

    // 提交到新分支
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['commit', '-m', `Optimized: ${currentCommitMessage} (history removed)`], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => {
        console.log('✅ 新分支提交完成')
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 删除原分支
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['branch', '-D', currentBranch], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => resolve())
      proc.on('error', () => resolve())
    })

    // 重命名新分支为原分支名
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['branch', '-m', currentBranch], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => {
        console.log(`✅ 分支重命名为 ${currentBranch} 完成`)
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 5. 删除所有reflog（引用日志）
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

    // 6. 删除所有远程跟踪分支引用（除了当前分支）
    console.log('🗑️ 删除其他远程跟踪分支引用...')
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
            .filter(ref => !ref.includes(`refs/remotes/origin/${currentBranch}`)) // 保留当前分支的远程引用
          console.log(`发现需要删除的远程引用: ${refs.join(', ')}`)
          resolve(refs)
        } else {
          resolve([])
        }
      })
      proc.on('error', () => resolve([]))
    })

    // 逐个删除其他远程引用
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

    // 7. 重新配置远程仓库，只跟踪当前分支
    console.log(`🔧 重新配置远程仓库，只跟踪分支: ${currentBranch}`)

    // 清除现有的fetch配置
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['config', '--unset-all', 'remote.origin.fetch'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => resolve())
      proc.on('error', () => resolve())
    })

    // 设置只拉取当前分支的配置
    const targetRefspec = `+refs/heads/${currentBranch}:refs/remotes/origin/${currentBranch}`
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['config', '--add', 'remote.origin.fetch', targetRefspec], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => {
        console.log(`✅ 设置单分支fetch配置: ${targetRefspec}`)
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 8. 转换为浅克隆仓库（如果还不是）
    console.log('🔄 转换为浅克隆仓库...')
    await new Promise<void>(resolve => {
      const proc = spawn(gitPath, ['config', 'core.repositoryformatversion', '0'], {
        stdio: 'pipe',
        env: gitEnv,
        cwd: repoPath,
      })
      proc.on('close', () => resolve())
      proc.on('error', () => resolve())
    })

    // 创建shallow文件，标记为浅克隆
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
        console.log('✅ 创建shallow文件，标记为浅克隆')
      } catch (error) {
        console.log('⚠️ 创建shallow文件失败:', error)
      }
    }

    // 9. 执行激进的垃圾回收和压缩
    console.log('🧹 执行激进垃圾回收和压缩...')
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

    // 10. 重新打包仓库以最小化存储
    console.log('📦 重新打包仓库以最小化存储...')
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

    console.log('✅ 极致存储优化完成：只保留当前分支最新commit，删除所有历史数据和其他分支')
  } catch (error) {
    console.error('❌ 极致存储优化失败:', error)
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
        message: '开始下载源码包...',
      })
    }

    const { downloadFile } = await import('./downloadService')
    await downloadFile(sourceUrl, downloadPath)

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
