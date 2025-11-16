import {
  ALL_MIRRORS,
  API_ENDPOINTS,
  type MirrorConfig,
  type MirrorCategory,
  getMirrorUrl,
  getDefaultMirror,
} from '@/config/mirrors'

/**
 * 镜像源管理器类
 */
export class MirrorManager {
  private static instance: MirrorManager
  private mirrorConfigs: MirrorCategory = { ...ALL_MIRRORS }
  private apiEndpoints = { ...API_ENDPOINTS }
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
   * 初始化镜像管理器（使用本地配置，云端获取功能已禁用）
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) {
      return
    }

    // 使用本地配置
    this.mirrorConfigs = { ...ALL_MIRRORS }
    this.apiEndpoints = { ...API_ENDPOINTS }
    this.isInitialized = true
    console.log('镜像管理器初始化完成（使用本地配置）')
  }

  /**
   * 获取配置状态
   */
  getConfigStatus() {
    return {
      source: 'local' as const,
      version: 'local',
    }
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
   * 获取默认镜像源（推荐的或第一个）
   */
  getDefaultMirror(type: keyof MirrorCategory): MirrorConfig | null {
    return getDefaultMirror(type)
  }

  /**
   * 获取API端点
   */
  getApiEndpoint(key: keyof typeof API_ENDPOINTS): string {
    return this.apiEndpoints[key]
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
   * 获取所有镜像源配置（用于导出或备份）
   */
  getAllConfigs() {
    return {
      mirrors: this.mirrorConfigs,
      apiEndpoints: this.apiEndpoints,
    }
  }
}

// 导出单例实例
export const mirrorManager = MirrorManager.getInstance()

// 导出便捷函数
export const getMirrors = (type: keyof MirrorCategory) => mirrorManager.getMirrors(type)
export const getMirrorUrlByManager = (type: keyof MirrorCategory, key: string) =>
  mirrorManager.getMirrorUrl(type, key)
