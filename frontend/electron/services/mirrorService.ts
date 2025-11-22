/**
 * 镜像源管理服务 V2
 * 重构版本 - 独立实现，不依赖旧有方法
 */

import * as fs from 'fs'
import * as path from 'path'
import * as https from 'https'
import * as http from 'http'

// ==================== 类型定义 ====================

export interface MirrorSource {
    name: string
    url: string
    type: 'official' | 'mirror'
    description: string
}

export interface MirrorConfig {
    python: MirrorSource[]
    get_pip: MirrorSource[]
    git: MirrorSource[]
    repo: MirrorSource[]
    pip_mirror: MirrorSource[]
}

export interface CloudMirrorConfig {
    version: string
    lastUpdated: string
    mirrors: MirrorConfig
}

// ==================== 默认镜像源配置 ====================

const DEFAULT_MIRROR_CONFIG: MirrorConfig = {
    python: [
        {
            name: '阿里云镜像',
            url: 'https://mirrors.aliyun.com/python-release/windows/python-3.12.0-embed-amd64.zip',
            type: 'mirror',
            description: '阿里云镜像服务，国内访问速度快'
        },
        {
            name: '清华 TUNA 镜像',
            url: 'https://mirrors.tuna.tsinghua.edu.cn/python/3.12.0/python-3.12.0-embed-amd64.zip',
            type: 'mirror',
            description: '清华大学开源软件镜像站'
        },
        {
            name: 'Python 官方',
            url: 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip',
            type: 'official',
            description: 'Python 官方下载源'
        }
    ],
    get_pip: [
        {
            name: '自建下载站',
            url: 'https://download.auto-mas.top/d/AUTO-MAS/get-pip.py',
            type: 'mirror',
            description: '项目自建下载站'
        },
        {
            name: 'PyPA 官方',
            url: 'https://bootstrap.pypa.io/get-pip.py',
            type: 'official',
            description: 'PyPA 官方 get-pip 脚本'
        }
    ],
    git: [
        {
            name: '自建下载站',
            url: 'https://download.auto-mas.top/d/AUTO-MAS/git.zip',
            type: 'mirror',
            description: '项目自建下载站'
        }
    ],
    repo: [
        {
            name: 'Gitee 镜像',
            url: 'https://gitee.com/auto-mas-project/AUTO-MAS.git',
            type: 'mirror',
            description: 'Gitee 镜像源，国内访问速度快'
        },
        {
            name: 'GitHub 官方',
            url: 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
            type: 'official',
            description: 'GitHub 官方仓库'
        }
    ],
    pip_mirror: [
        {
            name: '阿里云',
            url: 'https://mirrors.aliyun.com/pypi/simple/',
            type: 'mirror',
            description: '阿里云 PyPI 镜像'
        },
        {
            name: '清华大学',
            url: 'https://pypi.tuna.tsinghua.edu.cn/simple/',
            type: 'mirror',
            description: '清华大学 PyPI 镜像'
        },
        {
            name: 'PyPI 官方',
            url: 'https://pypi.org/simple/',
            type: 'official',
            description: 'PyPI 官方源'
        }
    ]
}

// ==================== 镜像源管理类 ====================

export class MirrorServiceV2 {
    private mirrorConfig: MirrorConfig
    private localConfigPath: string

    constructor(appRoot: string) {
        this.localConfigPath = path.join(appRoot, 'config', 'mirror_config.json')
        this.mirrorConfig = { ...DEFAULT_MIRROR_CONFIG }
    }

    /**
     * 初始化镜像源配置
     * 尝试从云端下载，失败则使用本地默认配置
     */
    async initialize(): Promise<void> {
        console.log('=== 初始化镜像源配置 ===')

        try {
            // 尝试从云端下载配置
            const cloudConfig = await this.downloadCloudConfig()
            if (cloudConfig) {
                this.mirrorConfig = cloudConfig.mirrors
                this.saveLocalConfig(cloudConfig)
                console.log('✅ 成功从云端加载镜像源配置')
                return
            }
        } catch (error) {
            console.warn('⚠️ 从云端下载配置失败:', error)
        }

        // 尝试加载本地缓存配置
        try {
            const localConfig = this.loadLocalConfig()
            if (localConfig) {
                this.mirrorConfig = localConfig.mirrors
                console.log('✅ 使用本地缓存的镜像源配置')
                return
            }
        } catch (error) {
            console.warn('⚠️ 加载本地配置失败:', error)
        }

        // 使用默认配置
        console.log('✅ 使用默认镜像源配置')
    }

    /**
     * 从云端下载镜像源配置
     */
    private downloadCloudConfig(): Promise<CloudMirrorConfig | null> {
        return new Promise((resolve) => {
            const url = 'https://download.auto-mas.top/d/AUTO-MAS/Server/mirror.json'
            console.log(`正在从云端下载镜像源配置: ${url}`)

            const client = url.startsWith('https') ? https : http

            const req = client.get(url, { timeout: 10000 }, (response) => {
                if (response.statusCode !== 200) {
                    console.warn(`云端配置下载失败，状态码: ${response.statusCode}`)
                    resolve(null)
                    return
                }

                let data = ''
                response.on('data', (chunk) => {
                    data += chunk.toString()
                })

                response.on('end', () => {
                    try {
                        const config = JSON.parse(data) as CloudMirrorConfig
                        console.log(`✅ 云端配置下载成功，版本: ${config.version}`)
                        resolve(config)
                    } catch (error) {
                        console.error('解析云端配置失败:', error)
                        resolve(null)
                    }
                })
            })

            req.on('error', (error) => {
                console.warn('云端配置下载请求失败:', error.message)
                resolve(null)
            })

            req.on('timeout', () => {
                console.warn('云端配置下载超时')
                req.destroy()
                resolve(null)
            })
        })
    }

    /**
     * 保存配置到本地
     */
    private saveLocalConfig(config: CloudMirrorConfig): void {
        try {
            const configDir = path.dirname(this.localConfigPath)
            if (!fs.existsSync(configDir)) {
                fs.mkdirSync(configDir, { recursive: true })
            }
            fs.writeFileSync(this.localConfigPath, JSON.stringify(config, null, 2), 'utf-8')
            console.log('✅ 镜像源配置已保存到本地')
        } catch (error) {
            console.error('保存本地配置失败:', error)
        }
    }

    /**
     * 加载本地配置
     */
    private loadLocalConfig(): CloudMirrorConfig | null {
        try {
            if (!fs.existsSync(this.localConfigPath)) {
                return null
            }
            const data = fs.readFileSync(this.localConfigPath, 'utf-8')
            return JSON.parse(data) as CloudMirrorConfig
        } catch (error) {
            console.error('加载本地配置失败:', error)
            return null
        }
    }

    /**
     * 获取指定类型的镜像源列表
     */
    getMirrors(type: keyof MirrorConfig): MirrorSource[] {
        return this.mirrorConfig[type] || []
    }

    /**
     * 获取所有镜像源配置
     */
    getAllMirrors(): MirrorConfig {
        return { ...this.mirrorConfig }
    }
}
