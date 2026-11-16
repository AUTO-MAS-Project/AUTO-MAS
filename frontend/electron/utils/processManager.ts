import { exec } from 'child_process'
import * as path from 'path'
import { getAppRoot } from '../services/environmentService'

import { getLogger } from '../services/logger'
const logger = getLogger('进程管理')

interface ProcessInfo {
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
