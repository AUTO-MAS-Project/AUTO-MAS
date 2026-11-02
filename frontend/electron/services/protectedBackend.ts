import { getFluxdownInstallEnvironment } from './fluxdownInstallService'

const allowedPaths = new Set([
  '/api/setting/backup',
  '/api/setting/openclaw-qq/status',
  '/api/setting/openclaw-qq/groups',
  '/api/setting/openclaw-qq/target',
  '/api/setting/openclaw-qq/login/start',
  '/api/setting/openclaw-qq/login/check',
  '/api/setting/openclaw-qq/unbind',
  '/api/setting/openclaw-qq/credentials/get',
  '/api/setting/openclaw-qq/credentials/set',
])

/** 仅向固定的本机端点发送主进程持有的授权令牌。 */
export function fetchProtectedLocal(
  baseUrl: string,
  path: string,
  body?: Record<string, unknown>
): Promise<Response> {
  if (!allowedPaths.has(path)) throw new Error('不允许访问此后端操作')
  const url = new URL(path, baseUrl)
  if (
    url.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
    url.username ||
    url.password
  ) {
    throw new Error('敏感操作仅允许连接本机后端')
  }
  const { AUTO_MAS_INSTALL_TOKEN: token } = getFluxdownInstallEnvironment()
  return fetch(url, {
    method: path === '/api/setting/backup' ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    ...(path === '/api/setting/backup'
      ? {}
      : { body: JSON.stringify(body ?? {}), signal: AbortSignal.timeout(30_000) }),
    redirect: 'error',
  })
}
