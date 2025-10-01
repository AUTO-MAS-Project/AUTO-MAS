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

const gitDownloadUrl = 'https://download.auto-mas.top/d/AUTO_MAS/git.zip'

// 获取应用版本号
function getAppVersion(appRoot: string): string {
  console.log('=== 开始获取应用版本号 ===')
  console.log(`应用根目录: ${appRoot}`)

  try {
    // 方法1: 从 Electron app 获取版本号（打包后可用）
    try {
      const appVersion = app.getVersion()
      if (appVersion && appVersion !== '1.0.0') { // 避免使用默认版本
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
  repoUrl = 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git'
): Promise<{
  success: boolean
  error?: string
}> {
  console.log('=== 开始克隆/更新后端代码 ===')
  console.log(`应用根目录: ${appRoot}`)
  console.log(`仓库URL: ${repoUrl}`)

  try {
    const backendPath = appRoot
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')

    console.log(`Git可执行文件路径: ${gitPath}`)
    console.log(`后端代码路径: ${backendPath}`)

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
    const isRepo = isGitRepository(backendPath)
    console.log(`检查是否为Git仓库: ${isRepo ? '✅ 是' : '❌ 否'}`)

    // ==== 下面是关键逻辑 ====
    if (isRepo) {
      console.log('=== 更新现有Git仓库 ===')

      // 已是 git 仓库，先更新远程URL为镜像站，然后 pull
      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: `正在更新后端代码(分支: ${targetBranch})...`,
        })
      }

      // 更新远程URL为镜像站URL，避免直接访问GitHub
      console.log(`📡 更新远程URL为镜像站: ${repoUrl}`)
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['remote', 'set-url', 'origin', repoUrl], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: backendPath,
        })
        proc.stdout?.on('data', d => console.log('git remote set-url stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => console.log('git remote set-url stderr:', d.toString().trim()))
        proc.on('close', code => {
          console.log(`git remote set-url 退出码: ${code}`)
          if (code === 0) {
            console.log('✅ 远程URL更新成功')
            resolve()
          } else {
            console.error('❌ 远程URL更新失败')
            reject(new Error(`git remote set-url失败，退出码: ${code}`))
          }
        })
        proc.on('error', error => {
          console.error('❌ git remote set-url 进程错误:', error)
          reject(error)
        })
      })

      // 获取远程分支信息
      console.log('📥 获取远程分支信息...')
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['fetch', 'origin'], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: backendPath,
        })
        proc.stdout?.on('data', d => console.log('git fetch stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => console.log('git fetch stderr:', d.toString().trim()))
        proc.on('close', code => {
          console.log(`git fetch 退出码: ${code}`)
          if (code === 0) {
            console.log('✅ 远程分支信息获取成功')
            resolve()
          } else {
            console.error('❌ 远程分支信息获取失败')
            reject(new Error(`git fetch失败，退出码: ${code}`))
          }
        })
        proc.on('error', error => {
          console.error('❌ git fetch 进程错误:', error)
          reject(error)
        })
      })

      // 切换到目标分支
      console.log(`🔀 切换到目标分支: ${targetBranch}`)
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['checkout', '-B', targetBranch, `origin/${targetBranch}`], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: backendPath,
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

      // 执行pull操作
      console.log('⬇️ 拉取最新代码...')
      await new Promise<void>((resolve, reject) => {
        const proc = spawn(gitPath, ['pull'], { stdio: 'pipe', env: gitEnv, cwd: backendPath })
        proc.stdout?.on('data', d => console.log('git pull stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => console.log('git pull stderr:', d.toString().trim()))
        proc.on('close', code => {
          console.log(`git pull 退出码: ${code}`)
          if (code === 0) {
            console.log('✅ 代码拉取成功')
            resolve()
          } else {
            console.error('❌ 代码拉取失败')
            reject(new Error(`git pull失败，退出码: ${code}`))
          }
        })
        proc.on('error', error => {
          console.error('❌ git pull 进程错误:', error)
          reject(error)
        })
      })

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

      // 不是 git 仓库，clone 到 tmp，再拷贝出来
      const tmpDir = path.join(appRoot, 'git_tmp')
      console.log(`临时目录: ${tmpDir}`)

      if (fs.existsSync(tmpDir)) {
        console.log('🗑️ 清理现有临时目录...')
        fs.rmSync(tmpDir, { recursive: true, force: true })
      }

      console.log('📁 创建临时目录...')
      fs.mkdirSync(tmpDir, { recursive: true })

      if (mainWindow) {
        mainWindow.webContents.send('download-progress', {
          type: 'backend',
          progress: 0,
          status: 'downloading',
          message: `正在克隆后端代码(分支: ${targetBranch})...`,
        })
      }

      console.log(`📥 开始克隆代码到临时目录...`)
      console.log(`克隆参数: --single-branch --depth 1 --branch ${targetBranch}`)

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
            tmpDir,
          ],
          {
            stdio: 'pipe',
            env: gitEnv,
            cwd: appRoot,
          }
        )
        proc.stdout?.on('data', d => console.log('git clone stdout:', d.toString().trim()))
        proc.stderr?.on('data', d => console.log('git clone stderr:', d.toString().trim()))
        proc.on('close', code => {
          console.log(`git clone 退出码: ${code}`)
          if (code === 0) {
            console.log('✅ 代码克隆成功')
            resolve()
          } else {
            console.error('❌ 代码克隆失败')
            reject(new Error(`git clone失败，退出码: ${code}`))
          }
        })
        proc.on('error', error => {
          console.error('❌ git clone 进程错误:', error)
          reject(error)
        })
      })

      // 复制所有文件到 backendPath（appRoot），包含 .git
      console.log('📋 复制文件到目标目录...')
      const tmpFiles = fs.readdirSync(tmpDir)
      console.log(`临时目录中的文件: ${tmpFiles.join(', ')}`)

      for (const file of tmpFiles) {
        const src = path.join(tmpDir, file)
        const dst = path.join(backendPath, file)

        console.log(`复制: ${file}`)

        if (fs.existsSync(dst)) {
          console.log(`  - 删除现有文件/目录: ${dst}`)
          if (fs.statSync(dst).isDirectory()) fs.rmSync(dst, { recursive: true, force: true })
          else fs.unlinkSync(dst)
        }

        if (fs.statSync(src).isDirectory()) {
          console.log(`  - 复制目录: ${src} -> ${dst}`)
          copyDirSync(src, dst)
        } else {
          console.log(`  - 复制文件: ${src} -> ${dst}`)
          fs.copyFileSync(src, dst)
        }
      }

      console.log('🗑️ 清理临时目录...')
      fs.rmSync(tmpDir, { recursive: true, force: true })

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
