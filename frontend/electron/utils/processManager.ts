import { exec } from 'child_process'
import * as path from 'path'
import { getAppRoot } from '../services/environmentService'
import { logService } from '../services/logService'

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

    const appRoot = getAppRoot()
    const pythonExePath = path.join(appRoot, 'environment', 'python', 'python.exe')

    // 使用 wmic 获取详细的进程信息
    const cmd = `wmic process where "Name='python.exe' or Name='AUTO-MAS.exe' or CommandLine like '%main.py%'" get ProcessId,Name,CommandLine /format:csv`

    exec(cmd, (error, stdout, stderr) => {
      if (error) {
        logService.error('进程管理', `获取进程信息失败: ${error}`)
        resolve([])
        return
      }

      const processes: ProcessInfo[] = []
      const lines = stdout.split('\n').filter(line => line.trim() && !line.startsWith('Node'))

      for (const line of lines) {
        const parts = line.split(',')
        if (parts.length >= 4) {
          const commandLine = parts[1] || ''
          const name = parts[2] || ''
          const pid = parseInt(parts[3]) || 0

          if (
            pid > 0 &&
            (commandLine.includes(pythonExePath) ||
              commandLine.includes('main.py') ||
              name === 'AUTO-MAS.exe')
          ) {
            processes.push({ pid, name, commandLine })
          }
        }
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
        logService.error('进程管理', `结束进程 ${pid} 失败: ${error.message}`)
        resolve(false)
      } else {
        logService.info('进程管理', `进程 ${pid} 已结束`)
        resolve(true)
      }
    })
  })
}

/**
 * 强制结束所有相关进程
 */
export async function killAllRelatedProcesses(): Promise<void> {
  logService.info('进程管理', '开始清理所有相关进程...')

  const processes = await getRelatedProcesses()
  logService.info('进程管理', `找到 ${processes.length} 个相关进程:`)

  for (const proc of processes) {
    logService.info('进程管理', `- PID: ${proc.pid}, Name: ${proc.name}, CMD: ${proc.commandLine.substring(0, 100)}...`)
  }

  // 并行结束所有进程
  const killPromises = processes.map(proc => killProcess(proc.pid))
  await Promise.all(killPromises)

  logService.info('进程管理', '进程清理完成')
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
