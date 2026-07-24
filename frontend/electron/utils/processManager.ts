import { exec } from 'child_process'

import { getLogger } from '../services/logger'
const logger = getLogger('进程管理')

export interface ProcessInfo {
  pid: number
  name: string
  commandLine: string
}

/**
 * 兼容旧调用。系统范围的 Python/main.py 扫描已禁用；
 * 调用方应通过 BackendService 获取当前实例可证明归属的进程。
 */
export async function getRelatedProcesses(): Promise<ProcessInfo[]> {
  logger.warn('系统范围进程扫描已禁用，请使用 BackendService 的精确归属查询')
  return []
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
 * 兼容旧调用。广域进程结束已禁用。
 */
export async function killAllRelatedProcesses(): Promise<void> {
  logger.warn('系统范围进程清理已禁用，请使用 BackendService 的精确归属停止')
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
