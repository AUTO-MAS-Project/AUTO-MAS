/**
 * 镜像源管理工具
 * 提供动态获取和更新镜像源配置的功能
 */

import {
  ALL_MIRRORS,
  API_ENDPOINTS,
  DOWNLOAD_LINKS,
  type MirrorConfig,
  type MirrorCategory,
  getMirrorUrl,
  updateMirrorSpeed,
  sortMirrorsBySpeed,
  getFastestMirror,
} from '@/config/mirrors'
import { cloudConfigManager, type CloudMirrorConfig } from './cloudConfigManager'

/**
 * 镜像源管理器类
 */
export class MirrorManager {
  private static instance: MirrorManager
  private mirrorConfigs: MirrorCategory = { ...ALL_MIRRORS }
  private apiEndpoints = { ...API_ENDPOINTS }
  private downloadLinks = { ...DOWNLOAD_LINKS }
  private isInitialized = false

  private constructor() {}

  /**
   * 获取单例实例
   */
  static getInstance(): MirrorManager {
    if (!MirrorManager.instance) {
      MirrorManager.instance = new MirrorManager()
    }
    return MirrorManager.instance
  }

  /**
   * 初始化镜像管理器（从云端拉取配置）
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) {
      return
    }

    try {
      // 准备兜底配置
      const fallbackConfig: CloudMirrorConfig = {
        version: '1.0.0-local',
        lastUpdated: new Date().toISOString(),
        mirrors: { ...ALL_MIRRORS },
        apiEndpoints: { ...API_ENDPOINTS },
        downloadLinks: { ...DOWNLOAD_LINKS },
      }

      // 从云端初始化配置
      const config = await cloudConfigManager.initializeConfig(fallbackConfig)

      // 更新本地配置
      this.mirrorConfigs = config.mirrors
      this.apiEndpoints = config.apiEndpoints
      this.downloadLinks = config.downloadLinks

      this.isInitialized = true
      console.log('镜像管理器初始化完成')
    } catch (error) {
      console.error('镜像管理器初始化失败:', error)
      // 使用默认配置
      this.isInitialized = true
    }
  }

  /**
   * 手动刷新云端配置
   */
  async refreshCloudConfig(): Promise<{ success: boolean; error?: string }> {
    try {
      const result = await cloudConfigManager.refreshConfig()

      if (result.success && result.config) {
        // 更新本地配置
        this.mirrorConfigs = result.config.mirrors
        this.apiEndpoints = result.config.apiEndpoints
        this.downloadLinks = result.config.downloadLinks

        return { success: true }
      } else {
        return { success: false, error: result.error }
      }
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '刷新配置失败',
      }
    }
  }

  /**
   * 获取配置状态
   */
  getConfigStatus() {
    return cloudConfigManager.getConfigStatus()
  }

  /**
   * 获取指定类型的镜像源列表
   */
  getMirrors(type: keyof MirrorCategory): MirrorConfig[] {
    return this.mirrorConfigs[type] || []
  }

  /**
   * 获取镜像源URL
   */
  getMirrorUrl(type: keyof MirrorCategory, key: string): string {
    return getMirrorUrl(type, key)
  }

  /**
   * 更新镜像源速度
   */
  updateMirrorSpeed(type: keyof MirrorCategory, key: string, speed: number): void {
    updateMirrorSpeed(type, key, speed)
  }

  /**
   * 获取最快的镜像源
   */
  getFastestMirror(type: keyof MirrorCategory): MirrorConfig | null {
    return getFastestMirror(type)
  }

  /**
   * 按速度排序镜像源
   */
  sortMirrorsBySpeed(mirrors: MirrorConfig[]): MirrorConfig[] {
    return sortMirrorsBySpeed(mirrors)
  }

  /**
   * 测试镜像源速度
   */
  async testMirrorSpeed(url: string, timeout: number = 5000): Promise<number> {
    try {
      const startTime = Date.now()
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), timeout)

      const response = await fetch(url, {
        method: 'HEAD',
        signal: controller.signal,
        cache: 'no-cache',
      })

      clearTimeout(timeoutId)

      if (response.ok) {
        return Date.now() - startTime
      } else {
        return 9999 // 请求失败
      }
    } catch (error) {
      return 9999 // 超时或网络错误
    }
  }

  /**
   * 批量测试镜像源速度
   */
  async testAllMirrorSpeeds(type: keyof MirrorCategory): Promise<MirrorConfig[]> {
    const mirrors = this.getMirrors(type)
    const promises = mirrors.map(async mirror => {
      const speed = await this.testMirrorSpeed(mirror.url)
      this.updateMirrorSpeed(type, mirror.key, speed)
      return { ...mirror, speed }
    })

    const results = await Promise.all(promises)
    return this.sortMirrorsBySpeed(results)
  }

  /**
   * 获取API端点
   */
  getApiEndpoint(key: keyof typeof API_ENDPOINTS): string {
    return this.apiEndpoints[key]
  }

  /**
   * 获取下载链接
   */
  getDownloadLink(key: keyof typeof DOWNLOAD_LINKS): string {
    return this.downloadLinks[key] || ''
  }

  /**
   * 动态更新镜像源配置（用于从API获取最新配置）
   */
  updateMirrorConfig(type: keyof MirrorCategory, mirrors: MirrorConfig[]): void {
    this.mirrorConfigs[type] = mirrors
  }

  /**
   * 动态更新API端点配置
   */
  updateApiEndpoints(endpoints: Partial<typeof API_ENDPOINTS>): void {
    this.apiEndpoints = { ...this.apiEndpoints, ...endpoints }
  }

  /**
   * 从远程API获取镜像源配置
   */
  async fetchMirrorConfigFromApi(apiUrl: string): Promise<void> {
    try {
      const response = await fetch(`${apiUrl}/api/mirrors`)
      if (response.ok) {
        const config = await response.json()

        // 更新各类镜像源配置
        if (config.git) this.updateMirrorConfig('git', config.git)
        if (config.python) this.updateMirrorConfig('python', config.python)
        if (config.pip) this.updateMirrorConfig('pip', config.pip)

        // 更新API端点
        if (config.apiEndpoints) this.updateApiEndpoints(config.apiEndpoints)

        console.log('镜像源配置已从API更新')
      }
    } catch (error) {
      console.warn('从API获取镜像源配置失败:', error)
    }
  }

  /**
   * 获取所有镜像源配置（用于导出或备份）
   */
  getAllConfigs() {
    return {
      mirrors: this.mirrorConfigs,
      apiEndpoints: this.apiEndpoints,
      downloadLinks: this.downloadLinks,
    }
  }
}

// 导出单例实例
export const mirrorManager = MirrorManager.getInstance()

// 导出便捷函数
export const getMirrors = (type: keyof MirrorCategory) => mirrorManager.getMirrors(type)
export const getMirrorUrlByManager = (type: keyof MirrorCategory, key: string) =>
  mirrorManager.getMirrorUrl(type, key)
export const testMirrorSpeed = (url: string, timeout?: number) =>
  mirrorManager.testMirrorSpeed(url, timeout)
export const testAllMirrorSpeeds = (type: keyof MirrorCategory) =>
  mirrorManager.testAllMirrorSpeeds(type)
