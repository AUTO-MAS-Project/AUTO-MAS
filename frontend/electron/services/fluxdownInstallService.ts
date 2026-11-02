import { randomBytes } from 'crypto'

// 仅主进程和它启动的后端链路持有；不写配置、不放进 argv、不返回给 renderer。
const installToken = randomBytes(32).toString('hex')
const mirrors = new Set(['auto', 'official', 'ghproxy', 'ghfast', 'github'])

export function getFluxdownInstallEnvironment(): NodeJS.ProcessEnv {
  return { AUTO_MAS_INSTALL_TOKEN: installToken }
}

/** 目标端点来自主进程的后端发现，renderer 只能选择有限的镜像标识。 */
export async function installFluxdown(baseUrl: string, mirror: unknown): Promise<unknown> {
  if (typeof mirror !== 'string' || !mirrors.has(mirror)) {
    throw new Error('无效的 FluxDown 下载镜像')
  }
  const url = new URL('/api/update/fluxdown/install', baseUrl)
  if (
    url.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
    url.username ||
    url.password
  ) {
    throw new Error('FluxDown 安装仅允许连接本机 MAS 后端')
  }
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${installToken}`,
    },
    body: JSON.stringify({ mirror }),
    redirect: 'error',
    signal: AbortSignal.timeout(30 * 60 * 1000),
  })
  const result: unknown = await response.json()
  if (!response.ok) {
    const detail = result && typeof result === 'object' && 'detail' in result ? result.detail : null
    throw new Error(
      typeof detail === 'string' ? detail : `FluxDown 安装请求失败 (${response.status})`
    )
  }
  return result
}
