/**
 * 镜像源轮替框架
 * 重构版本 - 独立实现
 */

import { MirrorSource } from './mirrorService'

// 导入日志服务
import { logService } from './logService'

// 使用日志服务的日志记录器
const logger = {
    error: (message: string, ...args: any[]) => logService.error('镜像轮替服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    warn: (message: string, ...args: any[]) => logService.warn('镜像轮替服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    info: (message: string, ...args: any[]) => logService.info('镜像轮替服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    debug: (message: string, ...args: any[]) => logService.debug('镜像轮替服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    log: (message: string, ...args: any[]) => logService.info('镜像轮替服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`)
}

// ==================== 类型定义 ====================

export interface NetworkOperationProgress {
    progress: number // 百分比 0-100
    description: string
}

export type NetworkOperationCallback = (
    mirror: MirrorSource,
    onProgress: (progress: NetworkOperationProgress) => void
) => Promise<{ success: boolean; result?: any; error?: string }>

export interface MirrorRotationProgress {
    currentMirror: MirrorSource
    mirrorIndex: number
    totalMirrors: number
    operationProgress: NetworkOperationProgress
}

export type MirrorRotationProgressCallback = (progress: MirrorRotationProgress) => void

// ==================== 镜像源轮替类 ====================

export class MirrorRotationService {
    /**
     * 镜像源轮替执行
     * 按照配置文件镜像源 -> 镜像源列表的顺序依次尝试
     * 如果指定了 preferredMirrorName，则只使用该镜像源（用于重试场景）
     */
    async execute(
        mirrors: MirrorSource[],
        operation: NetworkOperationCallback,
        onProgress?: MirrorRotationProgressCallback,
        preferredMirrorName?: string
    ): Promise<{ success: boolean; result?: any; error?: string; usedMirror?: MirrorSource }> {
        logger.info('=== 开始镜像源轮替 ===')
        logger.info(`可用镜像源数量: ${mirrors.length}`)
        if (preferredMirrorName) {
            logger.info(`指定镜像源: ${preferredMirrorName}（仅使用该镜像源）`)
        }

        if (mirrors.length === 0) {
            return { success: false, error: '没有可用的镜像源' }
        }

        // 如果指定了镜像源，只使用该镜像源
        let sortedMirrors: MirrorSource[]
        if (preferredMirrorName) {
            const selectedMirror = mirrors.find(m => m.name === preferredMirrorName)
            if (!selectedMirror) {
                logger.error(`❌ 未找到指定的镜像源: ${preferredMirrorName}`)
                return { success: false, error: `未找到指定的镜像源: ${preferredMirrorName}` }
            }
            sortedMirrors = [selectedMirror]
            logger.info(`找到指定镜像源，将仅使用该镜像源进行操作`)
        } else {
            // 重新排序镜像源：优先使用配置的镜像源
            sortedMirrors = this.sortMirrors(mirrors, preferredMirrorName)
        }

        // 依次尝试每个镜像源
        for (let i = 0; i < sortedMirrors.length; i++) {
            const mirror = sortedMirrors[i]
            logger.info(`尝试镜像源 [${i + 1}/${sortedMirrors.length}]: ${mirror.name}`)
            logger.info(`URL: ${mirror.url}`)

            try {
                // 执行网络操作
                const result = await operation(mirror, (operationProgress) => {
                    // 上报进度
                    if (onProgress) {
                        onProgress({
                            currentMirror: mirror,
                            mirrorIndex: i,
                            totalMirrors: sortedMirrors.length,
                            operationProgress
                        })
                    }
                })

                if (result.success) {
                    logger.info(`镜像源 ${mirror.name} 操作成功`)
                    return {
                        success: true,
                        result: result.result,
                        usedMirror: mirror
                    }
                } else {
                    logger.warn(`⚠️ 镜像源 ${mirror.name} 操作失败: ${result.error}`)
                }
            } catch (error) {
                const errorMsg = error instanceof Error ? error.message : String(error)
                logger.error(`❌ 镜像源 ${mirror.name} 发生异常: ${errorMsg}`)
            }
        }

        // 所有镜像源都失败
        logger.error('❌ 所有镜像源都尝试失败')
        return {
            success: false,
            error: preferredMirrorName
                ? `镜像源 ${preferredMirrorName} 操作失败，请检查网络连接或尝试其他镜像源`
                : '所有镜像源都尝试失败，请检查网络连接或稍后重试'
        }
    }

    /**
     * 排序镜像源
     * 优先使用配置的镜像源，然后是镜像源，最后是官方源
     */
    private sortMirrors(mirrors: MirrorSource[], preferredMirrorName?: string): MirrorSource[] {
        const sorted = [...mirrors]

        sorted.sort((a, b) => {
            // 1. 优先使用配置的镜像源
            if (preferredMirrorName) {
                if (a.name === preferredMirrorName) return -1
                if (b.name === preferredMirrorName) return 1
            }

            // 2. 镜像源优先于官方源
            if (a.type === 'mirror' && b.type === 'official') return -1
            if (a.type === 'official' && b.type === 'mirror') return 1

            return 0
        })

        return sorted
    }

    /**
     * 测试镜像源可用性
     */
    async testMirror(
        mirror: MirrorSource,
        operation: NetworkOperationCallback
    ): Promise<{ success: boolean; responseTime?: number; error?: string }> {
        const startTime = Date.now()

        try {
            const result = await operation(mirror, () => { })

            if (result.success) {
                const responseTime = Date.now() - startTime
                return { success: true, responseTime }
            } else {
                return { success: false, error: result.error }
            }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 批量测试所有镜像源
     */
    async testAllMirrors(
        mirrors: MirrorSource[],
        operation: NetworkOperationCallback
    ): Promise<Array<{
        mirror: MirrorSource
        success: boolean
        responseTime?: number
        error?: string
    }>> {
        logger.info('=== 批量测试镜像源 ===')

        const results = await Promise.all(
            mirrors.map(async (mirror) => {
                const result = await this.testMirror(mirror, operation)
                return {
                    mirror,
                    ...result
                }
            })
        )

        // 按响应时间排序
        results.sort((a, b) => {
            if (!a.success) return 1
            if (!b.success) return -1
            return (a.responseTime || 0) - (b.responseTime || 0)
        })

        return results
    }
}
