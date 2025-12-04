/**
 * 日志文件管理器
 * 负责日志文件的轮转、压缩和清理
 */

import * as fs from 'fs'
import * as path from 'path'
import * as zlib from 'zlib'
import { getAppRoot } from '../services/environmentService'

// 导入日志服务
import { logService } from '../services/logService'

// 使用日志服务的日志记录器
const logger = {
    error: (message: string, ...args: any[]) => logService.error('日志文件管理器', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    warn: (message: string, ...args: any[]) => logService.warn('日志文件管理器', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    info: (message: string, ...args: any[]) => logService.info('日志文件管理器', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    debug: (message: string, ...args: any[]) => logService.debug('日志文件管理器', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    log: (message: string, ...args: any[]) => logService.info('日志文件管理器', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`)
}

export class LogFileManager {
    private static readonly DEBUG_DIR = 'debug'
    private static readonly CURRENT_LOG_FILE = 'frontend.log'
    private static readonly LOG_FILE_PATTERN = /^frontend\.log(\.\d{4}-\d{2}-\d+)?(\.gz)?$/

    // 获取debug目录路径
    public static getDebugDir(): string {
        const appRoot = getAppRoot()
        return path.join(appRoot, this.DEBUG_DIR)
    }

    // 获取当前日志文件路径
    static getCurrentLogPath(): string {
        return path.join(this.getDebugDir(), this.CURRENT_LOG_FILE)
    }

    // 获取历史日志文件路径
    private static getHistoryLogPath(date: Date): string {
        const dateStr = this.formatDateForFile(date)
        return path.join(this.getDebugDir(), `${this.CURRENT_LOG_FILE}.${dateStr}.gz`)
    }

    // 格式化日期为文件名格式
    private static formatDateForFile(date: Date): string {
        const year = date.getFullYear()
        const month = String(date.getMonth() + 1).padStart(2, '0')
        const day = String(date.getDate()).padStart(2, '0')
        return `${year}-${month}-${day}`
    }

    // 解析文件名中的日期
    private static parseDateFromFileName(fileName: string): Date | null {
        const match = fileName.match(/^frontend\.log\.(\d{4}-\d{2}-\d{2})\.gz$/)
        if (match) {
            const [, dateStr] = match
            const [year, month, day] = dateStr.split('-').map(Number)
            return new Date(year, month - 1, day)
        }
        return null
    }

    // 确保debug目录存在
    static ensureDebugDir(): void {
        const debugDir = this.getDebugDir()
        if (!fs.existsSync(debugDir)) {
            fs.mkdirSync(debugDir, { recursive: true })
        }
    }

    // 写入日志到当前日志文件
    static writeLog(content: string): void {
        this.ensureDebugDir()
        const logPath = this.getCurrentLogPath()

        try {
            fs.appendFileSync(logPath, content + '\n', 'utf8')
        } catch (error) {
            logger.error('写入日志文件失败:', error)
        }
    }

    // 获取当前日志文件内容
    static getCurrentLogContent(lines?: number): string {
        const logPath = this.getCurrentLogPath()

        if (!fs.existsSync(logPath)) {
            return ''
        }

        try {
            const content = fs.readFileSync(logPath, 'utf8')
            if (lines && lines > 0) {
                const allLines = content.split('\n').filter(line => line.trim() !== '')
                return allLines.slice(-lines).join('\n')
            }
            return content
        } catch (error) {
            logger.error('读取日志文件失败:', error)
            return ''
        }
    }

    // 获取所有日志文件列表
    static getLogFiles(): string[] {
        this.ensureDebugDir()
        const debugDir = this.getDebugDir()

        try {
            const files = fs.readdirSync(debugDir)
            return files
                .filter(file => this.LOG_FILE_PATTERN.test(file))
                .sort()
                .reverse() // 最新的在前面
        } catch (error) {
            logger.error('读取日志文件列表失败:', error)
            return []
        }
    }

    // 压缩日志文件
    private static async compressLogFile(sourcePath: string, targetPath: string): Promise<void> {
        return new Promise((resolve, reject) => {
            const gzip = zlib.createGzip({ level: 9 })
            const input = fs.createReadStream(sourcePath)
            const output = fs.createWriteStream(targetPath)

            output.on('close', () => {
                logger.info(`日志文件压缩完成: ${targetPath}`)
                resolve()
            })

            output.on('error', (err: Error) => {
                logger.error('压缩日志文件失败:', err)
                reject(err)
            })

            input.pipe(gzip).pipe(output)
        })
    }

    // 轮转日志文件（每周一次）
    static async rotateLog(): Promise<void> {
        const currentLogPath = this.getCurrentLogPath()

        // 检查当前日志文件是否存在且有内容
        if (!fs.existsSync(currentLogPath)) {
            return
        }

        const stats = fs.statSync(currentLogPath)
        if (stats.size === 0) {
            return
        }

        try {
            // 生成历史日志文件路径
            const now = new Date()
            const historyLogPath = this.getHistoryLogPath(now).replace('.zip', '.gz')

            // 压缩当前日志文件
            await this.compressLogFile(currentLogPath, historyLogPath)

            // 清空当前日志文件
            fs.writeFileSync(currentLogPath, '', 'utf8')

            logger.info(`日志轮转完成: ${historyLogPath}`)
        } catch (error) {
            logger.error('日志轮转失败:', error)
        }
    }

    // 清理旧日志文件（保留1个月）
    static cleanOldLogs(): void {
        this.ensureDebugDir()
        const debugDir = this.getDebugDir()

        try {
            const files = fs.readdirSync(debugDir)
            const now = new Date()
            const cutoffDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000) // 30天前

            files.forEach(file => {
                if (this.LOG_FILE_PATTERN.test(file) && file.endsWith('.gz')) {
                    const fileDate = this.parseDateFromFileName(file)
                    if (fileDate && fileDate < cutoffDate) {
                        const filePath = path.join(debugDir, file)
                        try {
                            fs.unlinkSync(filePath)
                            logger.info(`已删除旧日志文件: ${file}`)
                        } catch (error) {
                            logger.error(`删除旧日志文件失败: ${file}`, error)
                        }
                    }
                }
            })
        } catch (error) {
            logger.error('清理旧日志文件失败:', error)
        }
    }

    // 清空当前日志文件
    static clearCurrentLog(): void {
        const currentLogPath = this.getCurrentLogPath()

        try {
            fs.writeFileSync(currentLogPath, '', 'utf8')
            logger.info('当前日志文件已清空')
        } catch (error) {
            logger.error('清空当前日志文件失败:', error)
        }
    }

    // 获取日志文件内容
    static getLogContent(fileName?: string, lines?: number): string {
        if (!fileName || fileName === this.CURRENT_LOG_FILE) {
            return this.getCurrentLogContent(lines)
        }

        const filePath = path.join(this.getDebugDir(), fileName)

        if (!fs.existsSync(filePath)) {
            return ''
        }

        try {
            if (fileName.endsWith('.gz')) {
                // 对于压缩文件，解压读取
                const buffer = fs.readFileSync(filePath)
                const content = zlib.gunzipSync(buffer).toString('utf8')
                if (lines && lines > 0) {
                    const allLines = content.split('\n').filter(line => line.trim() !== '')
                    return allLines.slice(-lines).join('\n')
                }
                return content
            } else {
                const content = fs.readFileSync(filePath, 'utf8')
                if (lines && lines > 0) {
                    const allLines = content.split('\n').filter(line => line.trim() !== '')
                    return allLines.slice(-lines).join('\n')
                }
                return content
            }
        } catch (error) {
            logger.error('读取日志文件内容失败:', error)
            return ''
        }
    }

    // 检查是否需要轮转（每周检查一次）
    static shouldRotate(): boolean {
        const currentLogPath = this.getCurrentLogPath()

        if (!fs.existsSync(currentLogPath)) {
            return false
        }

        const stats = fs.statSync(currentLogPath)
        const fileAge = Date.now() - stats.mtime.getTime()
        const weekInMs = 7 * 24 * 60 * 60 * 1000

        // 检查文件是否超过一周且不为空
        return fileAge >= weekInMs && stats.size > 0
    }

    // 强制轮转日志（用于测试）
    static async forceRotate(): Promise<void> {
        await this.rotateLog()
    }
}