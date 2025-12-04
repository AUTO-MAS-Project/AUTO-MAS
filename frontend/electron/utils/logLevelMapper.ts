/**
 * 日志级别映射器
 * 用于后端loguru级别到前端LogLevel枚举的映射
 * 提供反向映射功能和级别验证
 */

import { LogLevel } from './logColors'

/**
 * 日志级别映射器配置接口
 */
export interface LogLevelMapperConfig {
    // 自定义级别映射
    customMapping?: Record<string, LogLevel>
    // 是否启用严格模式（严格模式下，未知级别会抛出错误）
    strictMode?: boolean
    // 默认级别（非严格模式下，未知级别使用此默认值）
    defaultLevel?: LogLevel
}

/**
 * 日志级别映射器类
 * 实现后端loguru级别到前端LogLevel枚举的映射
 */
export class LogLevelMapper {
    private static instance: LogLevelMapper
    private config: Required<LogLevelMapperConfig>

    // 默认的loguru到前端日志级别映射
    private static readonly DEFAULT_MAPPING: Record<string, LogLevel> = {
        'TRACE': LogLevel.TRACE,
        'DEBUG': LogLevel.DEBUG,
        'INFO': LogLevel.INFO,
        'SUCCESS': LogLevel.SUCCESS,  // 成功操作保持为独立的SUCCESS级别
        'WARN': LogLevel.WARN,  // WARN映射为WARN
        'WARNING': LogLevel.WARN,  // 兼容WARNING
        'ERROR': LogLevel.ERROR,
        'CRITICAL': LogLevel.CRITICAL,  // 严重错误保持为独立的CRITICAL级别
        'FATAL': LogLevel.ERROR  // 致命错误映射为ERROR
    }

    // 前端到后端的反向映射（一对多）
    private static readonly REVERSE_MAPPING: Record<LogLevel, string[]> = {
        [LogLevel.TRACE]: ['TRACE'],
        [LogLevel.DEBUG]: ['DEBUG'],
        [LogLevel.INFO]: ['INFO'],
        [LogLevel.SUCCESS]: ['SUCCESS'],  // SUCCESS级别保持独立
        [LogLevel.WARN]: ['WARN', 'WARNING'],  // WARN级别对应WARN和WARNING
        [LogLevel.ERROR]: ['ERROR', 'FATAL'],
        [LogLevel.CRITICAL]: ['CRITICAL']  // CRITICAL级别保持独立
    }

    private constructor(config: LogLevelMapperConfig = {}) {
        this.config = {
            customMapping: config.customMapping || {},
            strictMode: config.strictMode ?? false,
            defaultLevel: config.defaultLevel || LogLevel.INFO
        }
    }

    /**
     * 获取单例实例
     */
    static getInstance(config?: LogLevelMapperConfig): LogLevelMapper {
        if (!LogLevelMapper.instance) {
            LogLevelMapper.instance = new LogLevelMapper(config)
        }
        return LogLevelMapper.instance
    }

    /**
     * 将后端loguru级别映射到前端LogLevel
     * @param backendLevel 后端loguru级别
     * @returns 前端LogLevel
     */
    map(backendLevel: string): LogLevel {
        if (!backendLevel) {
            return this.handleUnknownLevel(backendLevel)
        }

        const normalizedLevel = backendLevel.toUpperCase().trim()

        // 优先使用自定义映射
        if (this.config.customMapping && this.config.customMapping[normalizedLevel]) {
            return this.config.customMapping[normalizedLevel]
        }

        // 使用默认映射
        const mappedLevel = LogLevelMapper.DEFAULT_MAPPING[normalizedLevel]
        if (mappedLevel) {
            return mappedLevel
        }

        // 处理未知级别
        return this.handleUnknownLevel(backendLevel)
    }

    /**
     * 将前端LogLevel反向映射到后端loguru级别
     * @param frontendLevel 前端LogLevel
     * @returns 可能的后端loguru级别数组
     */
    reverseMap(frontendLevel: LogLevel): string[] {
        return LogLevelMapper.REVERSE_MAPPING[frontendLevel] || []
    }

    /**
     * 验证后端级别是否有效
     * @param backendLevel 后端loguru级别
     * @returns 是否有效
     */
    isValidBackendLevel(backendLevel: string): boolean {
        if (!backendLevel) {
            return false
        }

        const normalizedLevel = backendLevel.toUpperCase().trim()

        // 检查默认映射
        if (LogLevelMapper.DEFAULT_MAPPING[normalizedLevel]) {
            return true
        }

        // 检查自定义映射
        return !!(this.config.customMapping && this.config.customMapping[normalizedLevel])
    }

    /**
     * 验证前端级别是否有效
     * @param frontendLevel 前端LogLevel
     * @returns 是否有效
     */
    isValidFrontendLevel(frontendLevel: LogLevel): boolean {
        return Object.values(LogLevel).includes(frontendLevel)
    }

    /**
     * 获取所有支持的后端级别
     * @returns 后端级别数组
     */
    getSupportedBackendLevels(): string[] {
        const defaultLevels = Object.keys(LogLevelMapper.DEFAULT_MAPPING)
        const customLevels = this.config.customMapping ? Object.keys(this.config.customMapping) : []
        return [...new Set([...defaultLevels, ...customLevels])]
    }

    /**
     * 获取所有支持的前端级别
     * @returns 前端LogLevel数组
     */
    getSupportedFrontendLevels(): LogLevel[] {
        return Object.values(LogLevel)
    }

    /**
     * 添加自定义级别映射
     * @param backendLevel 后端级别
     * @param frontendLevel 前端级别
     */
    addCustomMapping(backendLevel: string, frontendLevel: LogLevel): void {
        if (!this.config.customMapping) {
            this.config.customMapping = {}
        }
        this.config.customMapping[backendLevel.toUpperCase().trim()] = frontendLevel
    }

    /**
     * 移除自定义级别映射
     * @param backendLevel 后端级别
     */
    removeCustomMapping(backendLevel: string): void {
        if (this.config.customMapping) {
            delete this.config.customMapping[backendLevel.toUpperCase().trim()]
        }
    }

    /**
     * 更新配置
     * @param newConfig 新配置
     */
    updateConfig(newConfig: Partial<LogLevelMapperConfig>): void {
        this.config = { ...this.config, ...newConfig as Required<LogLevelMapperConfig> }
    }

    /**
     * 获取当前配置
     * @returns 当前配置
     */
    getConfig(): Required<LogLevelMapperConfig> {
        return { ...this.config }
    }

    /**
     * 重置为默认配置
     */
    resetToDefault(): void {
        this.config = {
            customMapping: {},
            strictMode: false,
            defaultLevel: LogLevel.INFO
        }
    }

    /**
     * 处理未知级别
     * @param backendLevel 未知的后端级别
     * @returns 映射后的前端LogLevel
     */
    private handleUnknownLevel(backendLevel: string): LogLevel {
        if (this.config.strictMode) {
            throw new Error(`未知的后端日志级别: ${backendLevel}`)
        }

        console.warn(`未知的后端日志级别: ${backendLevel}，使用默认级别: ${this.config.defaultLevel}`)
        return this.config.defaultLevel
    }

    /**
     * 获取映射统计信息
     * @returns 统计信息
     */
    getStats(): {
        totalBackendLevels: number
        totalFrontendLevels: number
        customMappingsCount: number
        mappingDetails: Array<{ backend: string; frontend: LogLevel; isCustom: boolean }>
    } {
        const mappingDetails: Array<{ backend: string; frontend: LogLevel; isCustom: boolean }> = []

        // 默认映射
        for (const [backend, frontend] of Object.entries(LogLevelMapper.DEFAULT_MAPPING)) {
            mappingDetails.push({ backend, frontend, isCustom: false })
        }

        // 自定义映射
        if (this.config.customMapping) {
            for (const [backend, frontend] of Object.entries(this.config.customMapping)) {
                mappingDetails.push({ backend, frontend, isCustom: true })
            }
        }

        return {
            totalBackendLevels: this.getSupportedBackendLevels().length,
            totalFrontendLevels: this.getSupportedFrontendLevels().length,
            customMappingsCount: this.config.customMapping ? Object.keys(this.config.customMapping).length : 0,
            mappingDetails
        }
    }
}

// 导出单例实例
export const logLevelMapper = LogLevelMapper.getInstance()

// 导出便捷函数
export const mapLogLevel = (backendLevel: string): LogLevel => {
    return logLevelMapper.map(backendLevel)
}

export const reverseMapLogLevel = (frontendLevel: LogLevel): string[] => {
    return logLevelMapper.reverseMap(frontendLevel)
}

export const isValidLogLevel = (backendLevel: string): boolean => {
    return logLevelMapper.isValidBackendLevel(backendLevel)
}