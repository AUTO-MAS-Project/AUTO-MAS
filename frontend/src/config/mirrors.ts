/**
 * 镜像源和下载链接配置文件
 * 集中管理所有下载用到的链接，方便后续通过接口动态配置
 */

export interface MirrorConfig {
  key: string
  name: string
  url: string
  speed?: number | null
}

export interface MirrorCategory {
  [key: string]: MirrorConfig[]
}

/**
 * Git 仓库镜像源配置
 */
export const GIT_MIRRORS: MirrorConfig[] = [
  {
    key: 'github',
    name: 'GitHub 官方',
    url: 'https://github.com/DLmaster361/AUTO_MAA.git',
    speed: null,
  },
  {
    key: 'ghfast',
    name: 'ghfast 镜像',
    url: 'https://ghfast.top/https://github.com/DLmaster361/AUTO_MAA.git',
    speed: null,
  },
  {
    key: 'ghproxy_cloudflare',
    name: 'gh-proxy (Cloudflare加速)',
    url: 'https://gh-proxy.com/https://github.com/DLmaster361/AUTO_MAA.git',
    speed: null,
  },
  {
    key: 'ghproxy_hongkong',
    name: 'gh-proxy (香港节点加速)',
    url: 'https://hk.gh-proxy.com/https://github.com/DLmaster361/AUTO_MAA.git',
    speed: null,
  },
  {
    key: 'ghproxy_fastly',
    name: 'gh-proxy (Fastly CDN加速)',
    url: 'https://cdn.gh-proxy.com/https://github.com/DLmaster361/AUTO_MAA.git',
    speed: null,
  },
  {
    key: 'ghproxy_edgeone',
    name: 'gh-proxy (EdgeOne加速）',
    url: 'https://edgeone.gh-proxy.com/https://github.com/DLmaster361/AUTO_MAA.git',
    speed: null,
  },
]

/**
 * Python 下载镜像源配置（3.12.0 embed版本）
 */
export const PYTHON_MIRRORS: MirrorConfig[] = [
  {
    key: 'official',
    name: 'Python 官方',
    url: 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip',
    speed: null,
  },
  {
    key: 'tsinghua',
    name: '清华 TUNA 镜像',
    url: 'https://mirrors.tuna.tsinghua.edu.cn/python/3.12.0/python-3.12.0-embed-amd64.zip',
    speed: null,
  },
  {
    key: 'huawei',
    name: '华为云镜像',
    url: 'https://mirrors.huaweicloud.com/repository/toolkit/python/3.12.0/python-3.12.0-embed-amd64.zip',
    speed: null,
  },
  {
    key: 'aliyun',
    name: '阿里云镜像',
    url: 'https://mirrors.aliyun.com/python-release/windows/python-3.12.0-embed-amd64.zip',
    speed: null,
  },
]

/**
 * PyPI pip 镜像源配置
 */
export const PIP_MIRRORS: MirrorConfig[] = [
  {
    key: 'official',
    name: 'PyPI 官方',
    url: 'https://pypi.org/simple/',
    speed: null,
  },
  {
    key: 'tsinghua',
    name: '清华大学',
    url: 'https://pypi.tuna.tsinghua.edu.cn/simple/',
    speed: null,
  },
  {
    key: 'ustc',
    name: '中科大',
    url: 'https://pypi.mirrors.ustc.edu.cn/simple/',
    speed: null,
  },
  {
    key: 'aliyun',
    name: '阿里云',
    url: 'https://mirrors.aliyun.com/pypi/simple/',
    speed: null,
  },
]

/**
 * API 服务端点配置
 */
export const API_ENDPOINTS = {
  // 本地开发服务器
  local: 'http://localhost:8000',
  // WebSocket连接基础URL
  websocket: 'ws://localhost:8000',
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
