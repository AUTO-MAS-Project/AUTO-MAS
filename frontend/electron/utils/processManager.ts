import { exec } from 'child_process'
import * as path from 'path'
import { getAppRoot } from '../services/environmentService'

import { getLogger } from '../services/logger'
const logger = getLogger('进程管理')

export interface ProcessInfo {
  pid: number
  name: string
  commandLine: string
}

const normalizeWindowsPath = (value: string): string => value.replace(/\//g, '\\').toLowerCase()

const processPathMarkers = (appRoot: string): string[] => {
  const root = path.resolve(appRoot)
  return [
    path.join(root, 'main.py'),
    path.join(root, '.venv', 'Scripts', 'python.exe'),
    path.join(root, 'environment', 'python', 'python.exe'),
  ].map(normalizeWindowsPath)
}

/**
 * 获取所有相关的进程信息
 */
export async function getRelatedProcesses(appRoot: string = getAppRoot()): Promise<ProcessInfo[]> {
  return new Promise((resolve, reject) => {
    if (process.platform !== 'win32') {
      resolve([])
      return
    }

    const pathMarkers = processPathMarkers(appRoot)

    // 使用 PowerShell 获取进程信息
    const psCommand = `
      Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -or 
        ($_.CommandLine -ne $null -and $_.CommandLine -like '*main.py*')
      } | Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress
    `.replace(/\n/g, ' ')

    exec(
      `powershell -NoProfile -Command "${psCommand}"`,
      { encoding: 'utf8' },
      (error, stdout, _stderr) => {
        if (error) {
          logger.error(`获取进程信息失败: ${error}`)
          reject(new Error(`获取进程信息失败: ${error.message}`))
          return
        }

        const processes: ProcessInfo[] = []

        try {
          if (!stdout.trim()) {
            resolve([])
            return
          }

          // PowerShell 返回的可能是单个对象或数组
          let parsed = JSON.parse(stdout.trim())
          if (!Array.isArray(parsed)) {
            parsed = [parsed]
          }

          for (const proc of parsed) {
            const pid = proc.ProcessId || 0
            const name = proc.Name || ''
            const commandLine = proc.CommandLine || ''
            const normalizedCommandLine = normalizeWindowsPath(commandLine)

            if (pid > 0 && pathMarkers.some(marker => normalizedCommandLine.includes(marker))) {
              processes.push({ pid, name, commandLine })
            }
          }
        } catch (parseError) {
          logger.error(`解析进程信息失败: ${parseError}`)
          reject(
            new Error(
              `解析进程信息失败: ${parseError instanceof Error ? parseError.message : String(parseError)}`
            )
          )
          return
        }

        resolve(processes)
      }
    )
  })
}

/**
 * 强制结束指定的进程
 */
export async function killProcess(pid: number): Promise<boolean> {
  return new Promise(resolve => {
    if (process.platform !== 'win32') {
      resolve(false)
      return
    }

    exec(`taskkill /f /t /pid ${pid}`, error => {
      if (error) {
        logger.error(`结束进程 ${pid} 失败: ${error.message}`)
        resolve(false)
      } else {
        logger.info(`进程 ${pid} 已结束`)
        resolve(true)
      }
    })
  })
}

/**
 * 强制结束所有相关进程
 */
export async function killAllRelatedProcesses(appRoot: string = getAppRoot()): Promise<void> {
  logger.info('开始清理所有相关进程...')

  const processes = await getRelatedProcesses(appRoot)
  logger.info(`找到 ${processes.length} 个相关进程:`)

  for (const proc of processes) {
    logger.info(
      `- PID: ${proc.pid}, Name: ${proc.name}, CMD: ${proc.commandLine.substring(0, 100)}...`
    )
  }

  // 并行结束所有进程
  const killResults = await Promise.all(processes.map(proc => killProcess(proc.pid)))
  const signalFailures = processes.filter((_, index) => !killResults[index])
  if (signalFailures.length > 0) {
    logger.warn(`有 ${signalFailures.length} 个 taskkill 命令失败，继续核对实际进程状态`)
  }

  const exitResults = await Promise.all(processes.map(proc => waitForProcessExit(proc.pid, 5000)))
  const unconfirmedPids = processes.filter((_, index) => !exitResults[index]).map(proc => proc.pid)
  const remainingProcesses = await getRelatedProcesses(appRoot)
  const remainingPids = remainingProcesses.map(proc => proc.pid)
  if (unconfirmedPids.length > 0 && remainingPids.length === 0) {
    logger.warn(
      `PID ${unconfirmedPids.join(', ')} 仍存在，但已不匹配 AUTO-MAS 后端身份，按 PID 复用处理`
    )
  }
  if (remainingPids.length > 0) {
    throw new Error(`无法确认相关进程已退出: PID ${remainingPids.join(', ')}`)
  }

  logger.info('进程清理完成')
}

/**
 * 等待进程结束
 */
export async function waitForProcessExit(pid: number, timeoutMs: number = 5000): Promise<boolean> {
  return new Promise(resolve => {
    const startTime = Date.now()

    const checkProcess = () => {
      if (Date.now() - startTime >= timeoutMs) {
        resolve(false)
        return
      }

      exec(`tasklist /fi "PID eq ${pid}" /fo csv /nh`, (error, stdout) => {
        if (error) {
          logger.warn(`核对进程 ${pid} 状态失败: ${error.message}`)
          setTimeout(checkProcess, 100)
          return
        }

        const exists = stdout.split(/\r?\n/).some(line => line.includes(`","${pid}","`))
        if (!exists) {
          resolve(true)
        } else {
          setTimeout(checkProcess, 100)
        }
      })
    }

    checkProcess()
  })
}
