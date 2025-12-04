/**
 * 后端日志格式化器
 * 将解析后的后端日志转换为前端日志格式
 * 支持前端界面输出
 * 实现纯文本格式化
 * 添加模板化格式支持
 */

import { ParsedLogEntry, LogLevel } from '../types/log'
import { LogLevelMapper } from './logLevelMapper'

/**
 * 格式化选项接口
 */
export interface FormatOptions {
    // 是否保留原始颜色
    preserveOriginalColors?: boolean
    // 是否添加前缀
    addPrefix?: string
    // 时间戳格式
    timestampFormat?: string
    // 是否包含模块名
    includeModule?: boolean
    // 是否包含级别
    includeLevel?: boolean
    // 是否包含时间戳
    includeTimestamp?: boolean
    // 自定义模板
    template?: string
    // 输出目标类型
    outputTarget?: 'console' | 'file' | 'frontend' | 'raw'
}

/**
 * 格式化请求选项接口
 */
export interface FormatRequestOptions extends FormatOptions {
    // 是否为批量格式化
    isBatch?: boolean
}

/**
 * 格式化结果接口
 */
export interface FormatResult {
    // 格式化后的文本
    formattedText: string
    // 是否包含颜色
    hasColors: boolean
    // 格式化耗时（毫秒）
    formattingTime: number
    // 使用的选项
    usedOptions: FormatRequestOptions
}

/**
 * 后端日志格式化器类
 */
export class BackendLogFormatter {
    private static instance: BackendLogFormatter
    private levelMapper: LogLevelMapper
    private defaultOptions: Required<FormatOptions>

    // 预定义的格式模板
    private static readonly TEMPLATES = {
        // 默认格式：时间戳 | 级别 | 模块 | 消息
        DEFAULT: '{timestamp} | {level} | {module} | {message}',

        // 简化格式：级别 - 消息
        SIMPLE: '{level} - {message}',

        // 详细格式：[时间戳] [级别] [模块] 消息
        DETAILED: '[{timestamp}] [{level}] [{module}] {message}',

        // JSON格式
        JSON: '{"timestamp": "{timestamp}", "level": "{level}", "module": "{module}", "message": "{message}"}',

        // 控制台格式（无颜色）
        CONSOLE: '{timestamp} | {level} | {module} | {message}',

        // 文件格式（无颜色）
        FILE: '{timestamp} | {level} | {module} | {message}'
    }

    private constructor(levelMapper?: LogLevelMapper) {
        this.levelMapper = levelMapper || LogLevelMapper.getInstance()

        this.defaultOptions = {
            preserveOriginalColors: false,
            addPrefix: '',
            timestampFormat: 'YYYY-MM-DD HH:mm:ss.SSS',
            includeModule: true,
            includeLevel: true,
            includeTimestamp: true,
            template: BackendLogFormatter.TEMPLATES.DEFAULT,
            outputTarget: 'frontend'
        }
    }

    /**
     * 获取单例实例
     */
    static getInstance(levelMapper?: LogLevelMapper): BackendLogFormatter {
        if (!BackendLogFormatter.instance) {
            BackendLogFormatter.instance = new BackendLogFormatter(levelMapper)
        }
        return BackendLogFormatter.instance
    }

    /**
     * 格式化单个日志条目
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 格式化结果
     */
    format(parsedLog: ParsedLogEntry, options: FormatRequestOptions = {}): FormatResult {
        const startTime = Date.now()

        // 合并选项
        const mergedOptions = this.mergeOptions(options)

        try {
            // 根据输出目标选择格式化方法
            let formattedText: string

            switch (mergedOptions.outputTarget) {
                case 'console':
                    formattedText = this.formatForConsole(parsedLog, mergedOptions)
                    break
                case 'file':
                    formattedText = this.formatForFile(parsedLog, mergedOptions)
                    break
                case 'frontend':
                    formattedText = this.formatForFrontend(parsedLog, mergedOptions)
                    break
                case 'raw':
                    formattedText = this.formatAsRaw(parsedLog, mergedOptions)
                    break
                default:
                    formattedText = this.formatDefault(parsedLog, mergedOptions)
            }

            // 添加前缀
            if (mergedOptions.addPrefix) {
                formattedText = `${mergedOptions.addPrefix}${formattedText}`
            }

            const endTime = Date.now()

            return {
                formattedText,
                hasColors: false, // 禁用颜色，始终返回false
                formattingTime: endTime - startTime,
                usedOptions: mergedOptions
            }
        } catch (error) {
            const errorMessage = `格式化失败: ${error instanceof Error ? error.message : String(error)}`
            console.error('BackendLogFormatter.format', errorMessage, parsedLog)

            return {
                formattedText: this.createFallbackFormat(parsedLog, mergedOptions),
                hasColors: false,
                formattingTime: Date.now() - startTime,
                usedOptions: mergedOptions
            }
        }
    }

    /**
     * 批量格式化日志条目
     * @param parsedLogs 解析后的日志条目数组
     * @param options 格式化选项
     * @returns 格式化结果数组
     */
    formatBatch(parsedLogs: ParsedLogEntry[], options: FormatRequestOptions = {}): FormatResult[] {
        const batchOptions = { ...options, isBatch: true }

        return parsedLogs.map(log => this.format(log, batchOptions))
    }

    /**
     * 格式化时间戳
     * @param timestamp 时间戳
     * @param format 时间格式
     * @returns 格式化后的时间字符串
     */
    private formatTimestamp(timestamp: Date, format: string): string {
        try {
            // 简单的时间格式化实现
            const year = timestamp.getFullYear()
            const month = String(timestamp.getMonth() + 1).padStart(2, '0')
            const day = String(timestamp.getDate()).padStart(2, '0')
            const hours = String(timestamp.getHours()).padStart(2, '0')
            const minutes = String(timestamp.getMinutes()).padStart(2, '0')
            const seconds = String(timestamp.getSeconds()).padStart(2, '0')
            const milliseconds = String(timestamp.getMilliseconds()).padStart(3, '0')

            return format
                .replace('YYYY', String(year))
                .replace('MM', month)
                .replace('DD', day)
                .replace('HH', hours)
                .replace('mm', minutes)
                .replace('ss', seconds)
                .replace('SSS', milliseconds)
        } catch (error) {
            console.error('BackendLogFormatter.formatTimestamp', '时间格式化失败', error)
            return timestamp.toISOString()
        }
    }

    /**
     * 为控制台输出格式化
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 格式化后的文本
     */
    private formatForConsole(parsedLog: ParsedLogEntry, options: Required<FormatOptions>): string {
        let template = options.template || BackendLogFormatter.TEMPLATES.CONSOLE

        // 如果保留原始颜色且存在彩色日志，直接使用
        if (options.preserveOriginalColors && parsedLog.coloredLog) {
            return parsedLog.coloredLog
        }

        // 否则重新格式化
        const replacements = this.buildReplacements(parsedLog, options)
        let formatted = this.replaceTemplate(template, replacements)

        return formatted
    }

    /**
     * 为文件输出格式化
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 格式化后的文本
     */
    private formatForFile(parsedLog: ParsedLogEntry, options: Required<FormatOptions>): string {
        let template = options.template || BackendLogFormatter.TEMPLATES.FILE

        // 文件输出不包含颜色
        const fileOptions = { ...options }
        const replacements = this.buildReplacements(parsedLog, fileOptions)

        return this.replaceTemplate(template, replacements)
    }

    /**
     * 为前端界面格式化
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 格式化后的文本
     */
    private formatForFrontend(parsedLog: ParsedLogEntry, options: Required<FormatOptions>): string {
        // 直接返回纯消息内容，不包含时间戳和级别信息
        // 让前端日志系统自己处理时间戳和级别的显示
        return parsedLog.message
    }

    /**
     * 原始格式化（不做任何处理）
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 原始文本
     */
    private formatAsRaw(parsedLog: ParsedLogEntry, options: Required<FormatOptions>): string {
        return parsedLog.originalLog || parsedLog.message || ''
    }

    /**
     * 默认格式化
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 格式化后的文本
     */
    private formatDefault(parsedLog: ParsedLogEntry, options: Required<FormatOptions>): string {
        const template = options.template || BackendLogFormatter.TEMPLATES.DEFAULT
        const replacements = this.buildReplacements(parsedLog, options)

        return this.replaceTemplate(template, replacements)
    }

    /**
     * 构建模板替换变量
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 替换变量对象
     */
    private buildReplacements(parsedLog: ParsedLogEntry, options: Required<FormatOptions>): Record<string, string> {
        const replacements: Record<string, string> = {}

        // 时间戳
        if (options.includeTimestamp) {
            replacements.timestamp = this.formatTimestamp(parsedLog.timestamp, options.timestampFormat)
        } else {
            replacements.timestamp = ''
        }

        // 级别
        if (options.includeLevel) {
            replacements.level = parsedLog.level
        } else {
            replacements.level = ''
        }

        // 模块
        if (options.includeModule) {
            replacements.module = parsedLog.module
        } else {
            replacements.module = ''
        }

        // 消息
        replacements.message = parsedLog.message

        return replacements
    }

    /**
     * 替换模板变量
     * @param template 模板字符串
     * @param replacements 替换变量
     * @returns 替换后的字符串
     */
    private replaceTemplate(template: string, replacements: Record<string, string>): string {
        let result = template

        for (const [key, value] of Object.entries(replacements)) {
            const regex = new RegExp(`\\{${key}\\}`, 'g')
            result = result.replace(regex, value)
        }

        return result
    }

    /**
     * 创建降级格式
     * @param parsedLog 解析后的日志条目
     * @param options 格式化选项
     * @returns 降级格式文本
     */
    private createFallbackFormat(parsedLog: ParsedLogEntry, options: Required<FormatOptions>): string {
        return `[格式化失败] ${parsedLog.timestamp.toISOString()} | ${parsedLog.level} | ${parsedLog.module} | ${parsedLog.message}`
    }

    /**
     * 合并选项
     * @param options 输入选项
     * @returns 合并后的选项
     */
    private mergeOptions(options: FormatRequestOptions): Required<FormatOptions> {
        return {
            ...this.defaultOptions,
            ...options,
            outputTarget: options.outputTarget || 'frontend'
        } as Required<FormatOptions>
    }

    /**
     * 设置默认选项
     * @param options 默认选项
     */
    setDefaultOptions(options: Partial<FormatOptions>): void {
        this.defaultOptions = { ...this.defaultOptions, ...options as Required<FormatOptions> }
    }

    /**
     * 获取默认选项
     * @returns 默认选项
     */
    getDefaultOptions(): Required<FormatOptions> {
        return { ...this.defaultOptions }
    }

    /**
     * 获取可用模板
     * @returns 模板对象
     */
    getTemplates(): Record<string, string> {
        return { ...BackendLogFormatter.TEMPLATES }
    }

    /**
     * 设置模板
     * @param name 模板名称
     * @param template 模板内容
     */
    setTemplate(name: string, template: string): void {
        (BackendLogFormatter.TEMPLATES as any)[name] = template
    }

    /**
     * 获取格式化统计信息
     * @returns 统计信息
     */
    getStats(): {
        supportedFormats: string[]
        supportedTemplates: string[]
        defaultOptions: Required<FormatOptions>
    } {
        return {
            supportedFormats: ['console', 'file', 'frontend', 'raw'],
            supportedTemplates: Object.keys(BackendLogFormatter.TEMPLATES),
            defaultOptions: this.defaultOptions
        }
    }
}

// 导出单例实例
export const backendLogFormatter = BackendLogFormatter.getInstance()

// 导出便捷函数
export const formatBackendLog = (parsedLog: ParsedLogEntry, options?: FormatRequestOptions): FormatResult => {
    return backendLogFormatter.format(parsedLog, options)
}

export const formatBackendLogs = (parsedLogs: ParsedLogEntry[], options?: FormatRequestOptions): FormatResult[] => {
    return backendLogFormatter.formatBatch(parsedLogs, options)
}