/**
 * 镜像源管理服务
 * 重构版本 - 独立实现，不依赖旧有方法
 */

import * as fs from 'fs'
import * as path from 'path'
import * as https from 'https'
import * as http from 'http'

// 导入日志服务
import { getLogger } from './logger'
const logger = getLogger('镜像源服务')

// ==================== 类型定义 ====================

export interface MirrorSource {
    key: string
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

export interface ApiEndpoints {
    local: string
    websocket: string
}

export interface CloudMirrorConfig {
    mirrors: MirrorConfig
    apiEndpoints?: ApiEndpoints  // API 端点配置
}

export interface LocalConfigCache {
    config: CloudMirrorConfig
    etag?: string  // 用于判断配置是否需要更新
    lastUpdated: string  // 最后更新时间
}

// ==================== 默认配置 ====================

const DEFAULT_API_ENDPOINTS: ApiEndpoints = {
    local: 'http://localhost:36163',
    websocket: 'ws://localhost:36163',
}

const DEFAULT_MIRROR_CONFIG: MirrorConfig = {
    python: [
        {
            key: 'aliyun',
            name: '阿里云镜像',
            url: 'https://mirrors.aliyun.com/python-release/windows/python-3.12.0-embed-amd64.zip',
            type: 'mirror',
            description: '阿里云镜像服务，国内访问速度快'
        },
        {
            key: 'tsinghua',
            name: '清华 TUNA 镜像',
            url: 'https://mirrors.tuna.tsinghua.edu.cn/python/3.12.0/python-3.12.0-embed-amd64.zip',
            type: 'mirror',
            description: '清华大学开源软件镜像站，国内访问速度快'
        },
        {
            key: 'autonas',
            name: 'AUTO-MAS 自建源',
            url: 'https://download.auto-mas.top/d/AUTO-MAS/Environment/python-3.12.0-embed-amd64.zip',
            type: 'mirror',
            description: 'AUTO-MAS 自建下载站，国内访问速度快'
        },
        {
            key: 'official',
            name: 'Python 官方',
            url: 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip',
            type: 'official',
            description: 'Python 官方下载源，在中国大陆连通性不佳'
        }
    ],
    get_pip: [
        {
            key: 'autonas',
            name: 'AUTO-MAS 自建源',
            url: 'https://download.auto-mas.top/d/AUTO-MAS/Environment/get-pip.py',
            type: 'mirror',
            description: 'AUTO-MAS 自建下载站，国内访问速度快'
        },
        {
            key: 'official',
            name: '官方源',
            url: 'https://bootstrap.pypa.io/get-pip.py',
            type: 'official',
            description: '官方源，在中国大陆连通性不佳'
        }
    ],
    git: [
        {
            key: 'autonas',
            name: 'AUTO-MAS 自建源',
            url: 'https://download.auto-mas.top/d/AUTO-MAS/Environment/git.zip',
            type: 'mirror',
            description: 'AUTO-MAS 自建下载站，国内访问速度快'
        }
    ],
    repo: [
        {
            key: 'gitee',
            name: 'Gitee 镜像',
            url: 'https://gitee.com/auto-mas-project/AUTO-MAS',
            type: 'mirror',
            description: 'Gitee 镜像源，更新会有少许延迟'
        },
        {
            key: 'ghproxy_cloudflare',
            name: 'gh-proxy (Cloudflare)',
            url: 'https://gh-proxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
            type: 'mirror',
            description: 'Cloudflare CDN 镜像，适合全球用户'
        },
        {
            key: 'github',
            name: 'GitHub 官方',
            url: 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
            type: 'official',
            description: '官方源，在中国大陆连通性不佳，可能需要科学上网'
        }
    ],
    pip_mirror: [
        {
            key: 'aliyun',
            name: '阿里云',
            url: 'https://mirrors.aliyun.com/pypi/simple/',
            type: 'mirror',
            description: '阿里云 PyPI 镜像，国内访问速度快'
        },
        {
            key: 'tsinghua',
            name: '清华大学',
            url: 'https://pypi.tuna.tsinghua.edu.cn/simple/',
            type: 'mirror',
            description: '清华大学 PyPI 镜像，国内访问速度快'
        },
        {
            key: 'ustc',
            name: '中科大',
            url: 'https://pypi.mirrors.ustc.edu.cn/simple/',
            type: 'mirror',
            description: '中科大 PyPI 镜像，国内访问稳定'
        },
        {
            key: 'official',
            name: 'PyPI 官方',
            url: 'https://pypi.org/simple/',
            type: 'official',
            description: 'PyPI 官方源，在中国大陆连通性不佳，下载速度慢'
        }
    ]
}

// ==================== 镜像源管理类 ====================

export class MirrorService {
    private mirrorConfig: MirrorConfig
    private apiEndpoints: ApiEndpoints
    private localConfigPath: string
    private currentEtag: string | undefined

    constructor(appRoot: string) {
        this.localConfigPath = path.join(appRoot, 'config', 'mirror_config.json')
        this.mirrorConfig = { ...DEFAULT_MIRROR_CONFIG }
        this.apiEndpoints = { ...DEFAULT_API_ENDPOINTS }
    }

    /**
     * 初始化镜像源配置
     * 使用 ETag 机制判断是否需要更新配置
     */
    async initialize(): Promise<void> {
        logger.info('=== 初始化镜像源配置 ===')

        // 先加载本地缓存配置和 ETag
        const localCache = this.loadLocalConfig()
        if (localCache) {
            this.mirrorConfig = localCache.config.mirrors
            this.apiEndpoints = localCache.config.apiEndpoints || DEFAULT_API_ENDPOINTS
            this.currentEtag = localCache.etag
            logger.info('加载本地缓存配置')
            logger.info(`ETag: ${this.currentEtag || '无'}`)
        }

        // 尝试从云端更新配置
        try {
            const result = await this.downloadCloudConfig(this.currentEtag)

            if (result.status === 'updated') {
                // 配置已更新
                this.mirrorConfig = result.config!.mirrors
                this.apiEndpoints = result.config!.apiEndpoints || DEFAULT_API_ENDPOINTS
                this.currentEtag = result.etag
                this.saveLocalConfig(result.config!, result.etag)
                logger.info('云端配置已更新')
                logger.info(`新 ETag: ${result.etag}`)
            } else if (result.status === 'not-modified') {
                // 配置未变化
                logger.info('云端配置未变化，使用缓存')
            } else {
                // 下载失败，使用已加载的缓存或默认配置
                if (!localCache) {
                    logger.info('使用默认镜像源配置')
                }
            }
        } catch (error) {
            logger.warn('⚠️ 检查云端配置失败:', error)
            if (!localCache) {
                logger.info('使用默认镜像源配置')
            }
        }

        logger.info(`API 端点: ${JSON.stringify(this.apiEndpoints)}`)
    }

    /**
     * 从云端下载镜像源配置（支持 ETag 条件请求）
     */
    private downloadCloudConfig(currentEtag?: string, url?: string): Promise<{
        status: 'updated' | 'not-modified' | 'error'
        config?: CloudMirrorConfig
        etag?: string
    }> {
        return new Promise((resolve) => {
            const targetUrl = url || 'https://api.auto-mas.top/file/Server/mirror.json'
            logger.info(`正在检查云端配置: ${targetUrl}`)
            if (currentEtag) {
                logger.info(`当前 ETag: ${currentEtag}`)
            }

            const client = targetUrl.startsWith('https') ? https : http
            const options: any = {
                timeout: 10000,
                headers: {}
            }

            // 如果有 ETag，添加 If-None-Match 头
            if (currentEtag) {
                options.headers['If-None-Match'] = currentEtag
            }

            const req = client.get(targetUrl, options, (response) => {
                // 处理重定向 (301, 302, 307, 308)
                if (response.statusCode && [301, 302, 307, 308].includes(response.statusCode)) {
                    const redirectUrl = response.headers.location
                    if (redirectUrl) {
                        logger.info(`跟随重定向: ${response.statusCode} -> ${redirectUrl}`)
                        req.destroy() // 销毁原请求
                        // 递归调用以跟随重定向，使用新的 URL
                        this.downloadCloudConfig(currentEtag, redirectUrl).then(resolve).catch(() => {
                            resolve({ status: 'error' })
                        })
                        return
                    }
                }

                const newEtag = response.headers['etag'] as string | undefined

                // 304 Not Modified - 配置未变化
                if (response.statusCode === 304) {
                    logger.info('云端配置未变化 (304 Not Modified)')
                    resolve({ status: 'not-modified' })
                    return
                }

                // 200 OK - 有新配置
                if (response.statusCode === 200) {
                    let data = ''
                    response.on('data', (chunk) => {
                        data += chunk.toString()
                    })

                    response.on('end', () => {
                        try {
                            const config = JSON.parse(data) as CloudMirrorConfig

                            // 确保 apiEndpoints 存在
                            if (!config.apiEndpoints) {
                                config.apiEndpoints = { ...DEFAULT_API_ENDPOINTS }
                            }

                            logger.info(`云端配置下载成功`)
                            if (newEtag) {
                                logger.info(`ETag: ${newEtag}`)
                            }

                            resolve({
                                status: 'updated',
                                config,
                                etag: newEtag
                            })
                        } catch (error) {
                            logger.error('解析云端配置失败:', error)
                            resolve({ status: 'error' })
                        }
                    })
                    return
                }

                // 其他状态码
                logger.warn(`云端配置请求失败，状态码: ${response.statusCode}`)
                resolve({ status: 'error' })
            })

            req.on('error', (error) => {
                logger.warn('云端配置请求失败:', error.message)
                resolve({ status: 'error' })
            })

            req.on('timeout', () => {
                logger.warn('云端配置请求超时')
                req.destroy()
                resolve({ status: 'error' })
            })
        })
    }

    /**
     * 保存配置到本地（包含 ETag）
     */
    private saveLocalConfig(config: CloudMirrorConfig, etag?: string): void {
        try {
            const configDir = path.dirname(this.localConfigPath)
            if (!fs.existsSync(configDir)) {
                fs.mkdirSync(configDir, { recursive: true })
            }

            const cache: LocalConfigCache = {
                config,
                etag,
                lastUpdated: new Date().toISOString()
            }

            fs.writeFileSync(this.localConfigPath, JSON.stringify(cache, null, 2), 'utf-8')
            logger.info('镜像源配置已保存到本地')
        } catch (error) {
            logger.error('保存本地配置失败:', error)
        }
    }

    /**
     * 加载本地配置（包含 ETag）
     */
    private loadLocalConfig(): LocalConfigCache | null {
        try {
            if (!fs.existsSync(this.localConfigPath)) {
                return null
            }
            const data = fs.readFileSync(this.localConfigPath, 'utf-8')
            const parsed = JSON.parse(data)

            // 兼容旧格式（直接是 CloudMirrorConfig）
            if (parsed.mirrors && !parsed.config) {
                logger.info('检测到旧格式配置，自动转换')
                return {
                    config: parsed as CloudMirrorConfig,
                    lastUpdated: new Date().toISOString()
                }
            }

            return parsed as LocalConfigCache
        } catch (error) {
            logger.error('加载本地配置失败:', error)
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

    /**
     * 获取 API 端点
     */
    getApiEndpoint(key: keyof ApiEndpoints): string {
        return this.apiEndpoints[key] || DEFAULT_API_ENDPOINTS[key]
    }

    /**
     * 获取所有 API 端点
     */
    getApiEndpoints(): ApiEndpoints {
        return { ...this.apiEndpoints }
    }

    /**
     * 更新 API 端点（运行时动态更新）
     */
    updateApiEndpoints(endpoints: Partial<ApiEndpoints>): void {
        this.apiEndpoints = { ...this.apiEndpoints, ...endpoints }
        logger.info(`API 端点已更新: ${JSON.stringify(this.apiEndpoints)}`)
    }
}
