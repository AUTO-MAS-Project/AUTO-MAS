/**
 * 日志格式化器
 * 实现与后端一致的日志格式
 * 格式: <green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan> | <level>{message}</level>
 */

import { ParsedLogEntry, LogLevel, LogSource } from '../types/log'
import { ColorProcessor } from './colorProcessor'
import {
    HEX_COLORS,
    getHexColor,
    LogLevel as ColorLogLevel,
    isValidLogLevel,
    parseLogLevel
} from './logColors'

export interface LogEntry {
    timestamp: Date
    level: string
    module: string
    message: string
}

// 颜色样式映射
interface ColorStyle {
    [key: string]: {
        color: string
        background?: string
        fontWeight?: string
    }
}

// 日志级别颜色映射 - 使用统一颜色配置
const LOG_LEVEL_COLORS: ColorStyle = {
    'TRACE': { color: HEX_COLORS.TRACE, background: '#f8f8f8', fontWeight: 'bold' },
    'DEBUG': { color: HEX_COLORS.DEBUG, background: '#f8f8f8', fontWeight: 'bold' },
    'INFO': { color: HEX_COLORS.INFO, background: '#f6ffed', fontWeight: 'bold' },
    'SUCCESS': { color: HEX_COLORS.SUCCESS, background: '#f6ffed', fontWeight: 'bold' },
    'WARN': { color: HEX_COLORS.WARN, background: '#fffbe6', fontWeight: 'bold' },
    'ERROR': { color: HEX_COLORS.ERROR, background: '#fff2f0', fontWeight: 'bold' },
    'CRITICAL': { color: HEX_COLORS.CRITICAL, background: '#fff2f0', fontWeight: 'bold' },
    'FATAL': { color: HEX_COLORS.CRITICAL, background: '#fff2f0', fontWeight: 'bold' }
}

// 模块颜色映射
const MODULE_COLORS: ColorStyle = {
    '后端': { color: '#1890ff', background: '#f0f5ff' },
    '前端': { color: '#722ed1', background: '#f9f0ff' },
    '系统': { color: '#13c2c2', background: '#e6fffb' }
}

// 缓存已格式化的字符串，提高性能
const formatCache = new Map<string, string>()
const MAX_CACHE_SIZE = 1000

export class LogFormatter {
    /**
     * 格式化日志条目，包含颜色标签
     * @param entry 日志条目
     * @returns 格式化后的日志字符串（带颜色标签）
     */
    static formatWithColors(entry: LogEntry): string {
        const cacheKey = `${entry.timestamp.getTime()}-${entry.level}-${entry.module}-${entry.message.substring(0, 50)}`

        // 检查缓存
        if (formatCache.has(cacheKey)) {
            return formatCache.get(cacheKey)!
        }

        const time = this.formatTimestamp(entry.timestamp)
        const level = this.formatLevel(entry.level)
        const module = entry.module
        const message = entry.message

        const formatted = `<green>${time}</green> | <level>${level}</level> | <cyan>${module}</cyan> | <level>${message}</level>`

        // 缓存结果
        if (formatCache.size >= MAX_CACHE_SIZE) {
            // 清理最早的缓存项
            const firstKey = formatCache.keys().next().value
            if (firstKey) {
                formatCache.delete(firstKey)
            }
        }
        formatCache.set(cacheKey, formatted)

        return formatted
    }

    /**
     * 格式化ParsedLogEntry，支持新的接口
     * @param entry 解析后的日志条目
     * @param options 格式化选项
     * @returns 格式化后的日志字符串
     */
    static formatParsedLogEntry(
        entry: ParsedLogEntry,
        options: {
            includeColors?: boolean
            includeMetadata?: boolean
            htmlFormat?: boolean
        } = {}
    ): string {
        const {
            includeColors = true,
            includeMetadata = false,
            htmlFormat = false
        } = options

        // 如果已经有带颜色的日志，直接返回
        if (entry.coloredLog && includeColors) {
            return entry.coloredLog
        }

        const time = this.formatTimestamp(entry.timestamp)
        const level = this.formatLevel(entry.level)
        const module = entry.module
        const message = entry.message

        if (htmlFormat && includeColors) {
            // HTML格式，使用内联样式
            const timeStyle = 'color: #00ff00; font-weight: bold;' // 使用loguru一致的绿色
            const levelStyle = this.getLevelStyle(entry.level)
            const moduleStyle = this.getModuleStyle(entry.module, entry.source)

            let formatted = `<span style="${timeStyle}">${time}</span> | <span style="${levelStyle}">${level}</span> | <span style="${moduleStyle}">${module}</span> | <span style="color: inherit;">${message}</span>`

            // 添加元数据
            if (includeMetadata && entry.metadata) {
                const metadataStr = JSON.stringify(entry.metadata)
                formatted += ` <span style="color: #999999; font-size: 0.9em;">[${metadataStr}]</span>`
            }

            return formatted
        } else if (includeColors) {
            // 标签格式
            let formatted = `<green>${time}</green> | <level>${level}</level> | <cyan>${module}</cyan> | <level>${message}</level>`

            // 添加元数据
            if (includeMetadata && entry.metadata) {
                const metadataStr = JSON.stringify(entry.metadata)
                formatted += ` <gray>[${metadataStr}]</gray>`
            }

            return formatted
        } else {
            // 无颜色格式
            let formatted = `${time} | ${level} | ${module} | ${message}`

            // 添加元数据
            if (includeMetadata && entry.metadata) {
                const metadataStr = JSON.stringify(entry.metadata)
                formatted += ` [${metadataStr}]`
            }

            return formatted
        }
    }

    /**
     * 格式化日志条目，不包含颜色标签（用于文件存储）
     * @param entry 日志条目
     * @returns 格式化后的日志字符串（无颜色）
     */
    static formatWithoutColors(entry: LogEntry): string {
        const time = this.formatTimestamp(entry.timestamp)
        const level = this.formatLevel(entry.level)
        const module = entry.module
        const message = entry.message

        return `${time} | ${level} | ${module} | ${message}`
    }

    /**
     * 格式化时间戳为 YYYY-MM-DD HH:mm:ss.SSS 格式
     * @param timestamp 时间戳
     * @returns 格式化后的时间字符串
     */
    static formatTimestamp(timestamp: Date): string {
        const year = timestamp.getFullYear()
        const month = String(timestamp.getMonth() + 1).padStart(2, '0')
        const day = String(timestamp.getDate()).padStart(2, '0')
        const hours = String(timestamp.getHours()).padStart(2, '0')
        const minutes = String(timestamp.getMinutes()).padStart(2, '0')
        const seconds = String(timestamp.getSeconds()).padStart(2, '0')
        const milliseconds = String(timestamp.getMilliseconds()).padStart(3, '0')

        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}.${milliseconds}`
    }

    /**
     * 格式化日志级别，固定宽度为8个字符
     * @param level 日志级别
     * @returns 格式化后的日志级别
     */
    static formatLevel(level: string | LogLevel): string {
        // 确保日志级别为8个字符宽度，左对齐
        return level.toString().padEnd(8, ' ')
    }

    /**
     * 获取日志级别对应的HTML样式
     * @param level 日志级别
     * @returns HTML样式字符串
     */
    static getLevelStyle(level: string | LogLevel): string {
        const levelStr = level.toString().toUpperCase()
        let style = LOG_LEVEL_COLORS[levelStr]

        // 如果在本地映射中找不到，尝试使用统一颜色配置
        if (!style) {
            // 尝试解析为ColorLogLevel
            const parsedLevel = parseLogLevel(levelStr)
            if (parsedLevel) {
                const color = getHexColor(parsedLevel)
                // 根据级别确定背景色
                let backgroundColor = '#f8f8f8' // 默认背景色
                if (parsedLevel === ColorLogLevel.INFO || parsedLevel === ColorLogLevel.SUCCESS) {
                    backgroundColor = '#f6ffed'
                } else if (parsedLevel === ColorLogLevel.WARN) {
                    backgroundColor = '#fffbe6'
                } else if (parsedLevel === ColorLogLevel.ERROR || parsedLevel === ColorLogLevel.CRITICAL) {
                    backgroundColor = '#fff2f0'
                }

                style = {
                    color,
                    background: backgroundColor,
                    fontWeight: 'bold'
                }
            } else {
                // 如果无法解析，使用INFO级别作为默认
                style = LOG_LEVEL_COLORS['INFO']
            }
        }

        return `color: ${style.color}; background-color: ${style.background}; padding: 2px 6px; border-radius: 3px; font-weight: ${style.fontWeight || 'bold'};`
    }

    /**
     * 获取模块对应的HTML样式
     * @param module 模块名
     * @param source 日志来源
     * @returns HTML样式字符串
     */
    static getModuleStyle(module: string, source?: LogSource): string {
        // 根据来源确定颜色
        let styleKey = module
        if (source) {
            switch (source) {
                case LogSource.BACKEND:
                    styleKey = '后端'
                    break
                case LogSource.FRONTEND:
                    styleKey = '前端'
                    break
                case LogSource.SYSTEM:
                    styleKey = '系统'
                    break
            }
        }

        const style = MODULE_COLORS[styleKey] || MODULE_COLORS['系统']
        return `color: ${style.color}; background-color: ${style.background}; padding: 2px 6px; border-radius: 3px; font-weight: ${style.fontWeight || 'bold'};`
    }

    /**
     * 创建日志条目
     * @param level 日志级别
     * @param module 模块名
     * @param message 日志消息
     * @returns 日志条目
     */
    static createLogEntry(level: string, module: string, message: string): LogEntry {
        return {
            timestamp: new Date(),
            level: level.toUpperCase(),
            module,
            message
        }
    }

    /**
     * 创建ParsedLogEntry
     * @param level 日志级别
     * @param module 模块名
     * @param message 日志消息
     * @param source 日志来源
     * @param originalLog 原始日志
     * @param metadata 元数据
     * @returns 解析后的日志条目
     */
    static createParsedLogEntry(
        level: LogLevel,
        module: string,
        message: string,
        source: LogSource = LogSource.SYSTEM,
        originalLog: string = '',
        metadata?: Record<string, any>
    ): ParsedLogEntry {
        return {
            timestamp: new Date(),
            level,
            module,
            message,
            source,
            originalLog,
            isValid: true,
            metadata
        }
    }

    /**
     * 清空格式化缓存
     */
    static clearCache(): void {
        formatCache.clear()
    }

    /**
     * 获取缓存大小
     */
    static getCacheSize(): number {
        return formatCache.size
    }

    /**
     * 批量格式化日志条目
     * @param entries 日志条目数组
     * @param options 格式化选项
     * @returns 格式化后的日志字符串数组
     */
    static formatBatch(
        entries: (LogEntry | ParsedLogEntry)[],
        options: {
            includeColors?: boolean
            includeMetadata?: boolean
            htmlFormat?: boolean
        } = {}
    ): string[] {
        return entries.map(entry => {
            if ('source' in entry) {
                // ParsedLogEntry
                return this.formatParsedLogEntry(entry as ParsedLogEntry, options)
            } else {
                // LogEntry
                if (options.htmlFormat && options.includeColors) {
                    const timeStyle = 'color: #00ff00; font-weight: bold;' // 使用loguru一致的绿色
                    const levelStyle = this.getLevelStyle(entry.level)
                    const moduleStyle = this.getModuleStyle(entry.module)

                    return `<span style="${timeStyle}">${this.formatTimestamp(entry.timestamp)}</span> | <span style="${levelStyle}">${this.formatLevel(entry.level)}</span> | <span style="${moduleStyle}">${entry.module}</span> | <span style="color: inherit;">${entry.message}</span>`
                } else if (options.includeColors) {
                    return this.formatWithColors(entry)
                } else {
                    return this.formatWithoutColors(entry)
                }
            }
        })
    }
}