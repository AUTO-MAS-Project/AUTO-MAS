/**
 * 镜像源和下载链接配置文件
 * 集中管理所有下载用到的链接，方便后续通过接口动态配置
 */

export interface MirrorConfig {
  key: string
  name: string
  url: string
  speed?: number | null
  type: 'official' | 'mirror'
  chinaConnectivity?: 'poor' | 'good' | 'excellent'
  description?: string
  recommended?: boolean
}

export interface MirrorCategory {
  [key: string]: MirrorConfig[]
}

/**
 * Git 仓库官方源配置
 */
export const GIT_OFFICIAL_MIRRORS: MirrorConfig[] = [
  {
    key: 'github',
    name: 'GitHub 官方',
    url: 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
    speed: null,
    type: 'official',
    chinaConnectivity: 'poor',
    description: '官方源，在中国大陆连通性不佳，可能需要科学上网',
  },
]

/**
 * Git 仓库镜像源配置
 */
export const GIT_MIRROR_MIRRORS: MirrorConfig[] = [
  {
    key: 'ghproxy_cloudflare',
    name: 'gh-proxy (Cloudflare)',
    url: 'https://gh-proxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'good',
    description: 'Cloudflare CDN 镜像，适合全球用户',
    recommended: true,
  },
  {
    key: 'ghproxy_fastly',
    name: 'gh-proxy (Fastly CDN)',
    url: 'https://cdn.gh-proxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'good',
    description: 'Fastly CDN 镜像服务',
  },
  {
    key: 'ghproxy_edgeone',
    name: 'gh-proxy (EdgeOne)',
    url: 'https://edgeone.gh-proxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'good',
    description: 'EdgeOne 镜像服务',
  },
  {
    key: 'ghfast',
    name: 'ghfast 镜像',
    url: 'https://ghfast.top/https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'good',
    description: '第三方镜像服务',
  },
]

/**
 * Git 仓库所有镜像源配置（按类型分组）
 */
export const GIT_MIRRORS: MirrorConfig[] = [
  ...GIT_MIRROR_MIRRORS,
  ...GIT_OFFICIAL_MIRRORS,
]

/**
 * Python 官方源配置（3.12.0 embed版本）
 */
export const PYTHON_OFFICIAL_MIRRORS: MirrorConfig[] = [
  {
    key: 'official',
    name: 'Python 官方',
    url: 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip',
    speed: null,
    type: 'official',
    chinaConnectivity: 'poor',
    description: 'Python 官方下载源，在中国大陆连通性不佳',
  },
]

/**
 * Python 镜像源配置（3.12.0 embed版本）
 */
export const PYTHON_MIRROR_MIRRORS: MirrorConfig[] = [
  {
    key: 'aliyun',
    name: '阿里云镜像',
    url: 'https://mirrors.aliyun.com/python-release/windows/python-3.12.0-embed-amd64.zip',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '阿里云镜像服务，国内访问速度快',
    recommended: true,
  },
  {
    key: 'tsinghua',
    name: '清华 TUNA 镜像',
    url: 'https://mirrors.tuna.tsinghua.edu.cn/python/3.12.0/python-3.12.0-embed-amd64.zip',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '清华大学开源软件镜像站，国内访问速度快',
  },
  {
    key: 'huawei',
    name: '华为云镜像',
    url: 'https://mirrors.huaweicloud.com/repository/toolkit/python/3.12.0/python-3.12.0-embed-amd64.zip',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '华为云镜像服务，国内访问稳定',
  },
]

/**
 * Python 下载所有镜像源配置（按类型分组）
 */
export const PYTHON_MIRRORS: MirrorConfig[] = [
  ...PYTHON_MIRROR_MIRRORS,
  ...PYTHON_OFFICIAL_MIRRORS,
]

/**
 * PyPI pip 官方源配置
 */
export const PIP_OFFICIAL_MIRRORS: MirrorConfig[] = [
  {
    key: 'official',
    name: 'PyPI 官方',
    url: 'https://pypi.org/simple/',
    speed: null,
    type: 'official',
    chinaConnectivity: 'poor',
    description: 'PyPI 官方源，在中国大陆连通性不佳，下载速度慢',
  },
]

/**
 * PyPI pip 镜像源配置
 */
export const PIP_MIRROR_MIRRORS: MirrorConfig[] = [
  {
    key: 'aliyun',
    name: '阿里云',
    url: 'https://mirrors.aliyun.com/pypi/simple/',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '阿里云 PyPI 镜像，国内访问速度快',
    recommended: true,
  },
  {
    key: 'tsinghua',
    name: '清华大学',
    url: 'https://pypi.tuna.tsinghua.edu.cn/simple/',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '清华大学 PyPI 镜像，国内访问速度快',
  },
  {
    key: 'ustc',
    name: '中科大',
    url: 'https://pypi.mirrors.ustc.edu.cn/simple/',
    speed: null,
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '中科大 PyPI 镜像，国内访问稳定',
  },
]

/**
 * PyPI pip 所有镜像源配置（按类型分组）
 */
export const PIP_MIRRORS: MirrorConfig[] = [
  ...PIP_MIRROR_MIRRORS,
  ...PIP_OFFICIAL_MIRRORS,
]

/**
 * API 服务端点配置
 */
export const API_ENDPOINTS = {
  // 本地开发服务器
  local: 'http://localhost:36163',
  // WebSocket连接基础URL
  websocket: 'ws://localhost:36163',
  // 代理服务器示例
  proxy: 'http://127.0.0.1:7890',
}

/**
 * 自建下载站链接配置
 */
export const DOWNLOAD_LINKS = {
  // get-pip.py 下载链接
  getPip: 'http://221.236.27.82:10197/d/AUTO_MAA/get-pip.py',

  // Git 客户端下载链接
  git: 'http://221.236.27.82:10197/d/AUTO_MAA/git.zip',
}

/**
 * 所有镜像源配置的集合
 */
export const ALL_MIRRORS: MirrorCategory = {
  git: GIT_MIRRORS,
  python: PYTHON_MIRRORS,
  pip: PIP_MIRRORS,
}

/**
 * 根据类型获取镜像源配置
 */
export function getMirrorsByType(type: keyof MirrorCategory): MirrorConfig[] {
  return ALL_MIRRORS[type] || []
}

/**
 * 根据类型和key获取特定镜像源URL
 */
export function getMirrorUrl(type: keyof MirrorCategory, key: string): string {
  const mirrors = getMirrorsByType(type)
  const mirror = mirrors.find(m => m.key === key)
  return mirror?.url || mirrors[0]?.url || ''
}

/**
 * 获取默认镜像源（通常是第一个）
 */
export function getDefaultMirror(type: keyof MirrorCategory): MirrorConfig | null {
  const mirrors = getMirrorsByType(type)
  return mirrors.length > 0 ? mirrors[0] : null
}

/**
 * 更新镜像源速度测试结果
 */
export function updateMirrorSpeed(type: keyof MirrorCategory, key: string, speed: number): void {
  const mirrors = getMirrorsByType(type)
  const mirror = mirrors.find(m => m.key === key)
  if (mirror) {
    mirror.speed = speed
  }
}

/**
 * 根据速度排序镜像源
 */
export function sortMirrorsBySpeed(mirrors: MirrorConfig[]): MirrorConfig[] {
  return [...mirrors].sort((a, b) => {
    const speedA = a.speed === null ? 9999 : a.speed
    const speedB = b.speed === null ? 9999 : b.speed
    return speedA - speedB
  })
}

/**
 * 获取最快的镜像源
 */
export function getFastestMirror(type: keyof MirrorCategory): MirrorConfig | null {
  const mirrors = getMirrorsByType(type)
  const sortedMirrors = sortMirrorsBySpeed(mirrors)
  return sortedMirrors.find(m => m.speed !== null && m.speed !== 9999) || null
}

/**
 * 根据类型筛选镜像源
 */
export function getMirrorsBySourceType(
  type: keyof MirrorCategory, 
  sourceType: 'official' | 'mirror'
): MirrorConfig[] {
  const mirrors = getMirrorsByType(type)
  return mirrors.filter(m => m.type === sourceType)
}

/**
 * 获取官方源（标注中国大陆连通性）
 */
export function getOfficialMirrors(type: keyof MirrorCategory): MirrorConfig[] {
  return getMirrorsBySourceType(type, 'official')
}

/**
 * 获取镜像源
 */
export function getMirrorMirrors(type: keyof MirrorCategory): MirrorConfig[] {
  return getMirrorsBySourceType(type, 'mirror')
}

/**
 * 获取推荐的镜像源
 */
export function getRecommendedMirrors(type: keyof MirrorCategory): MirrorConfig[] {
  const mirrors = getMirrorsByType(type)
  return mirrors.filter(m => m.recommended === true)
}

/**
 * 根据速度排序镜像源（推荐的排在前面）
 */
export function sortMirrorsBySpeedAndRecommendation(mirrors: MirrorConfig[]): MirrorConfig[] {
  return [...mirrors].sort((a, b) => {
    // 推荐的排在前面
    if (a.recommended && !b.recommended) return -1
    if (!a.recommended && b.recommended) return 1
    
    // 然后按速度排序
    const speedA = a.speed === null ? 9999 : a.speed
    const speedB = b.speed === null ? 9999 : b.speed
    return speedA - speedB
  })
}

/**
 * 根据中国大陆连通性筛选镜像源
 */
export function getMirrorsByChinaConnectivity(
  type: keyof MirrorCategory,
  connectivity: 'poor' | 'good' | 'excellent'
): MirrorConfig[] {
  const mirrors = getMirrorsByType(type)
  return mirrors.filter(m => m.chinaConnectivity === connectivity)
}

/**
 * 获取适合中国大陆用户的镜像源（排除连通性差的）
 */
export function getChinaFriendlyMirrors(type: keyof MirrorCategory): MirrorConfig[] {
  const mirrors = getMirrorsByType(type)
  return mirrors.filter(m => m.chinaConnectivity !== 'poor')
}
