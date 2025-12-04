/**
 * 云端配置管理器
 * 负责从云端拉取最新的镜像站配置，如果失败则使用本地兜底配置
 */

import type { CloudMirrorConfig } from '@/types/mirror'
import { getLogger } from '@/utils/logger'

const logger = getLogger('云端配置管理器')

export class CloudConfigManager {
  private static instance: CloudConfigManager
  private cloudConfigUrl = 'https://download.auto-mas.top/d/AUTO-MAS/Server/mirrors.json'
  private fallbackConfig: CloudMirrorConfig | null = null
  private currentConfig: CloudMirrorConfig | null = null
  private fetchTimeout = 10000 // 10秒超时

  private constructor() { }

  static getInstance(): CloudConfigManager {
    if (!CloudConfigManager.instance) {
      CloudConfigManager.instance = new CloudConfigManager()
    }
    return CloudConfigManager.instance
  }

  /**
   * 设置兜底配置（本地配置）
   */
  setFallbackConfig(config: CloudMirrorConfig): void {
    this.fallbackConfig = config
  }

  /**
   * 从云端拉取最新配置
   */
  async fetchCloudConfig(): Promise<CloudMirrorConfig | null> {
    const startTime = Date.now()

    try {
      logger.info(`正在从云端拉取镜像站配置... (超时时间: ${this.fetchTimeout}ms)`)
      logger.info(`请求URL: ${this.cloudConfigUrl}`)

      const controller = new AbortController()
      const timeoutId = setTimeout(() => {
        logger.warn(`网络请求超时 (${this.fetchTimeout}ms)`)
        controller.abort()
      }, this.fetchTimeout)

      const response = await fetch(this.cloudConfigUrl, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Cache-Control': 'no-cache',
        },
        signal: controller.signal,
      })

      clearTimeout(timeoutId)
      const responseTime = Date.now() - startTime

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const config: CloudMirrorConfig = await response.json()

      // 验证配置格式
      if (!this.validateConfig(config)) {
        throw new Error('云端配置格式不正确')
      }

      this.currentConfig = config
      logger.info(`云端配置拉取成功 (耗时: ${responseTime}ms, 版本: ${config.version})`)
      return config
    } catch (error) {
      const responseTime = Date.now() - startTime
      if (error instanceof Error && error.name === 'AbortError') {
        logger.warn(`云端配置拉取超时 (耗时: ${responseTime}ms)`)
      } else {
        logger.warn(`云端配置拉取失败 (耗时: ${responseTime}ms):`, error)
      }
      return null
    }
  }

  /**
   * 验证配置格式是否正确
   */
  private validateConfig(config: any): config is CloudMirrorConfig {
    if (!config || typeof config !== 'object') {
      return false
    }

    // 检查必需字段
    if (!config.version || !config.mirrors || !config.apiEndpoints || !config.downloadLinks) {
      return false
    }

    // 检查mirrors结构
    if (typeof config.mirrors !== 'object') {
      return false
    }

    // 检查每个镜像类型的配置
    for (const [type, mirrors] of Object.entries(config.mirrors)) {
      if (!Array.isArray(mirrors)) {
        return false
      }

      // 检查每个镜像配置
      for (const mirror of mirrors as any[]) {
        if (!mirror.key || !mirror.name || !mirror.url || !mirror.type) {
          return false
        }
      }
    }

    return true
  }

  /**
   * 获取当前有效配置（优先云端，兜底本地）
   */
  getCurrentConfig(): CloudMirrorConfig | null {
    return this.currentConfig || this.fallbackConfig
  }

  /**
   * 初始化配置（启动时调用）
   */
  async initializeConfig(fallbackConfig: CloudMirrorConfig): Promise<CloudMirrorConfig> {
    this.setFallbackConfig(fallbackConfig)

    // 尝试拉取云端配置，增加重试机制
    let cloudConfig = await this.fetchCloudConfig()

    // 如果第一次失败，等待2秒后重试一次
    if (!cloudConfig) {
      logger.info('首次拉取云端配置失败，2秒后重试...')
      await new Promise(resolve => setTimeout(resolve, 2000))
      cloudConfig = await this.fetchCloudConfig()
    }

    if (cloudConfig) {
      logger.info('使用云端配置')
      return cloudConfig
    } else {
      logger.info('云端配置拉取失败，使用本地兜底配置')
      return fallbackConfig
    }
  }

  /**
   * 手动刷新配置
   */
  async refreshConfig(): Promise<{ success: boolean; config?: CloudMirrorConfig; error?: string }> {
    try {
      const cloudConfig = await this.fetchCloudConfig()

      if (cloudConfig) {
        return { success: true, config: cloudConfig }
      } else {
        return {
          success: false,
          error: '无法获取云端配置，继续使用当前配置',
          config: this.getCurrentConfig() || undefined,
        }
      }
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        config: this.getCurrentConfig() || undefined,
      }
    }
  }

  /**
   * 获取配置状态信息
   */
  getConfigStatus(): {
    isUsingCloudConfig: boolean
    version?: string
    lastUpdated?: string
    source: 'cloud' | 'fallback'
  } {
    const config = this.getCurrentConfig()

    return {
      isUsingCloudConfig: this.currentConfig !== null,
      version: config?.version,
      lastUpdated: config?.lastUpdated,
      source: this.currentConfig ? 'cloud' : 'fallback',
    }
  }
}

// 导出单例实例
export const cloudConfigManager = CloudConfigManager.getInstance()
