/**
 * 镜像源类型定义
 * 与后端 mirrorService.ts 保持一致
 */

export interface MirrorSource {
    name: string
    url: string
    type: 'official' | 'mirror'
    description: string
}

/**
 * 前端扩展的镜像源配置（用于UI展示）
 */
export interface MirrorConfig extends MirrorSource {
    key: string
    speed?: number | null
    recommended?: boolean
}

export interface MirrorCategory {
    [key: string]: MirrorConfig[]
}

/**
 * 云端镜像源配置
 */
export interface CloudMirrorConfig {
    version: string
    lastUpdated: string
    mirrors: {
        python: MirrorSource[]
        get_pip: MirrorSource[]
        git: MirrorSource[]
        repo: MirrorSource[]
        pip_mirror: MirrorSource[]
    }
    apiEndpoints?: {
        local: string
        websocket: string
    }
    downloadLinks?: {
        getPip: string
        git: string
    }
}
