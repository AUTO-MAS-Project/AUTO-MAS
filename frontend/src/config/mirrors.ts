/**
 * 镜像源和下载链接配置文件
 * 集中管理所有下载用到的链接，方便后续通过接口动态配置
 */

export interface MirrorConfig {
  key: string
  name: string
  url: string
  speed?: number | null // Optional speed test result (kept for backward compatibility)
  type: 'official' | 'mirror'
  chinaConnectivity?: 'poor' | 'good' | 'excellent'
  description?: string
  recommended?: boolean
}

export interface MirrorCategory {
  [key: string]: MirrorConfig[]
}

/**
 * Git 仓库镜像源配置（官方源和镜像源合并，通过type区分）
 */
export const GIT_MIRRORS: MirrorConfig[] = [
  {
    key: 'gitee',
    name: 'Gitee 镜像',
    url: 'https://gitee.com/auto-mas-project/AUTO-MAS',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: 'Gitee 镜像源，更新会有少许延迟',
    recommended: true,
  },
  {
    key: 'github',
    name: 'GitHub 官方',
    url: 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git',
    type: 'official',
    chinaConnectivity: 'poor',
    description: '官方源，在中国大陆连通性不佳，可能需要科学上网',
  },
]

/**
 * Python 镜像源配置（官方源和镜像源合并，通过type区分）
 */
export const PYTHON_MIRRORS: MirrorConfig[] = [
  {
    key: 'aliyun',
    name: '阿里云镜像',
    url: 'https://mirrors.aliyun.com/python-release/windows/python-3.12.0-embed-amd64.zip',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '阿里云镜像服务，国内访问速度快',
    recommended: true,
  },
  {
    key: 'tsinghua',
    name: '清华 TUNA 镜像',
    url: 'https://mirrors.tuna.tsinghua.edu.cn/python/3.12.0/python-3.12.0-embed-amd64.zip',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '清华大学开源软件镜像站，国内访问速度快',
  },
  {
    key: 'huawei',
    name: '华为云镜像',
    url: 'https://mirrors.huaweicloud.com/repository/toolkit/python/3.12.0/python-3.12.0-embed-amd64.zip',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '华为云镜像服务，国内访问稳定',
  },
  {
    key: 'official',
    name: 'Python 官方',
    url: 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip',
    type: 'official',
    chinaConnectivity: 'poor',
    description: 'Python 官方下载源，在中国大陆连通性不佳',
  },
]

/**
 * PyPI pip 镜像源配置（官方源和镜像源合并，通过type区分）
 */
export const PIP_MIRRORS: MirrorConfig[] = [
  {
    key: 'aliyun',
    name: '阿里云',
    url: 'https://mirrors.aliyun.com/pypi/simple/',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '阿里云 PyPI 镜像，国内访问速度快',
    recommended: true,
  },
  {
    key: 'tsinghua',
    name: '清华大学',
    url: 'https://pypi.tuna.tsinghua.edu.cn/simple/',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '清华大学 PyPI 镜像，国内访问速度快',
  },
  {
    key: 'ustc',
    name: '中科大',
    url: 'https://pypi.mirrors.ustc.edu.cn/simple/',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: '中科大 PyPI 镜像，国内访问稳定',
  },
  {
    key: 'official',
    name: 'PyPI 官方',
    url: 'https://pypi.org/simple/',
    type: 'official',
    chinaConnectivity: 'poor',
    description: 'PyPI 官方源，在中国大陆连通性不佳，下载速度慢',
  },
]

/**
 * get-pip.py 下载源配置（官方源和镜像源合并，通过type区分）
 */
export const GET_PIP_MIRRORS: MirrorConfig[] = [
  {
    key: 'auto-mas',
    name: 'AUTO-MAS 下载站',
    url: 'https://download.auto-mas.top/d/AUTO_MAA/get-pip.py',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: 'AUTO-MAS 自建下载站，国内访问速度快',
    recommended: true,
  },
  {
    key: 'official',
    name: 'PyPA 官方',
    url: 'https://bootstrap.pypa.io/get-pip.py',
    type: 'official',
    chinaConnectivity: 'poor',
    description: 'PyPA 官方下载源，在中国大陆连通性不佳',
  },
]

/**
 * Git 客户端下载源配置（官方源和镜像源合并，通过type区分）
 */
export const GIT_DOWNLOAD_MIRRORS: MirrorConfig[] = [
  {
    key: 'auto-mas',
    name: 'AUTO-MAS 下载站',
    url: 'https://download.auto-mas.top/d/AUTO_MAA/git.zip',
    type: 'mirror',
    chinaConnectivity: 'excellent',
    description: 'AUTO-MAS 自建下载站，国内访问速度快',
    recommended: true,
  },
  {
    key: 'official',
    name: 'Git 官方',
    url: 'https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/MinGit-2.43.0-64-bit.zip',
    type: 'official',
    chinaConnectivity: 'poor',
    description: 'Git 官方下载源，在中国大陆连通性不佳',
  },
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
 * 所有镜像源配置的集合
 */
export const ALL_MIRRORS: MirrorCategory = {
  git: GIT_MIRRORS,
  python: PYTHON_MIRRORS,
  pip: PIP_MIRRORS,
  getPip: GET_PIP_MIRRORS,
  gitDownload: GIT_DOWNLOAD_MIRRORS,
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
 * 获取默认镜像源（推荐的或第一个）
 */
export function getDefaultMirror(type: keyof MirrorCategory): MirrorConfig | null {
  const mirrors = getMirrorsByType(type)
  const recommended = mirrors.find(m => m.recommended === true)
  return recommended || (mirrors.length > 0 ? mirrors[0] : null)
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
 * 获取推荐的镜像源
 */
export function getRecommendedMirrors(type: keyof MirrorCategory): MirrorConfig[] {
  const mirrors = getMirrorsByType(type)
  return mirrors.filter(m => m.recommended === true)
}

/**
 * 获取适合中国大陆用户的镜像源（排除连通性差的）
 */
export function getChinaFriendlyMirrors(type: keyof MirrorCategory): MirrorConfig[] {
  const mirrors = getMirrorsByType(type)
  return mirrors.filter(m => m.chinaConnectivity !== 'poor')
}
