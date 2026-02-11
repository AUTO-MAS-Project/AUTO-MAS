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

/**
 * 获取所有相关的进程信息
 */
export async function getRelatedProcesses(): Promise<ProcessInfo[]> {
  return new Promise(resolve => {
    if (process.platform !== 'win32') {
      resolve([])
      return
    }

    const appRoot = getAppRoot().replace(/\\/g, '\\\\')

    // 使用 PowerShell 获取进程信息
    const psCommand = `
      Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -or 
        $_.Name -eq 'AUTO-MAS.exe' -or 
        ($_.CommandLine -ne $null -and $_.CommandLine -like '*main.py*')
      } | Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress
    `.replace(/\n/g, ' ')

    exec(`powershell -NoProfile -Command "${psCommand}"`, { encoding: 'utf8' }, (error, stdout, stderr) => {
      if (error) {
        logger.error(`获取进程信息失败: ${error}`)
        resolve([])
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

        const pythonExePath = path.join(getAppRoot(), 'environment', 'python', 'python.exe')

        for (const proc of parsed) {
          const pid = proc.ProcessId || 0
          const name = proc.Name || ''
          const commandLine = proc.CommandLine || ''

          if (
            pid > 0 &&
            (commandLine.includes(pythonExePath) ||
              commandLine.includes('main.py') ||
              name === 'AUTO-MAS.exe')
          ) {
            processes.push({ pid, name, commandLine })
          }
        }
      } catch (parseError) {
        logger.error(`解析进程信息失败: ${parseError}`)
      }

      resolve(processes)
    })
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
export async function killAllRelatedProcesses(): Promise<void> {
  logger.info('开始清理所有相关进程...')

  const processes = await getRelatedProcesses()
  logger.info(`找到 ${processes.length} 个相关进程:`)

  for (const proc of processes) {
    logger.info(`- PID: ${proc.pid}, Name: ${proc.name}, CMD: ${proc.commandLine.substring(0, 100)}...`)
  }

  // 并行结束所有进程
  const killPromises = processes.map(proc => killProcess(proc.pid))
  await Promise.all(killPromises)

  logger.info('进程清理完成')
}

/**
 * 等待进程结束
 */
export async function waitForProcessExit(pid: number, timeoutMs: number = 5000): Promise<boolean> {
  return new Promise(resolve => {
    const startTime = Date.now()

    const checkProcess = () => {
      if (Date.now() - startTime > timeoutMs) {
        resolve(false)
        return
      }

      exec(`tasklist /fi "PID eq ${pid}"`, (error, stdout) => {
        if (error || !stdout.includes(pid.toString())) {
          resolve(true)
        } else {
          setTimeout(checkProcess, 100)
        }
      })
    }

    checkProcess()
  })
}
