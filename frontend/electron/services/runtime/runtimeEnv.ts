/**
 * Runtime 子进程的环境变量覆盖
 *
 * 两项，都只在需要时才设，不去覆盖 Runtime 自己的默认值：
 * - 遥测：用户关闭匿名遥测时透传 `AUTO_MAS_TELEMETRY=disabled` 给 `auto-mas-runtime.exe`，
 *   让 Runtime 自己的上报也一并关闭；开启时不设该变量。`--offline` 是完全独立的网络开关
 *   （禁止任何联网尝试），不能拿来当遥测开关用；
 * - 开发标记：`development` 模式透传 `AUTO_MAS_ENV=development`。Runtime 把自己的环境原样交给
 *   `uv run` 再交给后端，后端 `main.py` 的 `is_development_environment()` 读到它就按开发环境
 *   关闭 Sentry 上报。受监督时端口、`/api/core/close`、工作目录忽略开发标记是契约，但遥测不该
 *   跟着变成生产；旧链路（Electron 自己 spawn python）早就这么注入，这里只是补齐新链路。
 *
 * 遥测开关的权威来源是后端持久化的 `GlobalConfig.Function.IfEnableTelemetry`
 * （`<dataRoot>/config/Config.json`），与 Electron 主进程自身 Sentry 开关（见 `../sentry.ts`
 * 的 `configureMainSentry`）读的是同一份配置、同一条「非 false 即视为开启」规则。`dataRoot`
 * 是用户数据根（`getAppRoot()`），不是 `--app-root`：`development` 模式下两者不是同一个目录。
 */

import * as fs from 'fs'
import * as path from 'path'

import { getLogger } from '../logger'
import type { RuntimeLaunchMode } from './launchConfig'

const logger = getLogger('Runtime环境变量')

/** 透传给 Runtime 的遥测开关环境变量名。 */
export const RUNTIME_TELEMETRY_ENV = 'AUTO_MAS_TELEMETRY'

/** 透传给 Runtime（再到后端）的运行环境标记变量名，与旧链路 `createBackendEnvironment` 同名。 */
export const RUNTIME_APP_ENV = 'AUTO_MAS_ENV'

/** 出站代理环境变量名；Go 的 `ProxyFromEnvironment` 与 uv 都认这两个。 */
export const RUNTIME_HTTP_PROXY_ENV = 'HTTP_PROXY'
export const RUNTIME_HTTPS_PROXY_ENV = 'HTTPS_PROXY'

/** 代理白名单环境变量名。 */
export const RUNTIME_NO_PROXY_ENV = 'NO_PROXY'

/**
 * 本机地址一律不过代理。
 *
 * Runtime 自己的就绪探测已经写死 `Proxy: nil`，但这两个变量会被 Runtime 原样传给
 * `uv run` 再传给后端，后端的 httpx/requests 默认 `trust_env=True`，本机回环若被
 * 代理接管会直接打断前后端互调。
 */
const LOCAL_NO_PROXY = '127.0.0.1,localhost,::1'

/** 允许透传的代理协议；其余一律拒绝。 */
const ALLOWED_PROXY_PROTOCOLS = new Set(['http:', 'https:', 'socks5:', 'socks5h:'])

/** 后端持久化配置里本模块用到的字段。 */
interface BackendConfigShape {
  Function?: { IfEnableTelemetry?: unknown }
  Update?: { ProxyAddress?: unknown }
}

/**
 * 读取后端持久化配置（`<dataRoot>/config/Config.json`）。
 *
 * 文件不存在、JSON 损坏、内容不是对象都返回空对象，由各字段自己决定缺省行为。
 * 注意 `JSON.parse('null')` 与 `JSON.parse('[]')` 都是合法的，不排掉的话取字段时会
 * 抛出去打断整条启动——这个函数的调用点正是「初始化卡住」时唯一还能跑的那段。
 */
function readBackendConfig(dataRoot: string): BackendConfigShape {
  try {
    const configPath = path.join(dataRoot, 'config', 'Config.json')
    if (!fs.existsSync(configPath)) return {}

    const parsed: unknown = JSON.parse(fs.readFileSync(configPath, 'utf8'))
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    return parsed as BackendConfigShape
  } catch (error) {
    logger.warn(
      `读取后端配置失败，按缺省处理: ${error instanceof Error ? error.message : String(error)}`
    )
    return {}
  }
}

/**
 * 读取后端持久化配置里的遥测开关。
 *
 * 字段缺失或配置读不出来都按开启处理——只有明确写了 `false` 才是用户关闭过。
 */
function isTelemetryEnabled(config: BackendConfigShape): boolean {
  return config.Function?.IfEnableTelemetry !== false
}

/** 已经带了协议前缀，不再补默认协议。 */
const PROXY_SCHEME_PATTERN = /^[a-z][a-z0-9+.-]*:\/\//i

/**
 * 只有长得像 `[凭据@]主机[:端口]` 的裸地址才补默认协议。
 *
 * 不能像后端那样对任何无协议输入无脑加 `http://`：WHATWG URL 在 special scheme 下
 * 把 `\` 当作 `/`，`http://D:\虚拟C盘\MuMuPlayer-12.0\nx_main` 会被解析成主机名 `d`，
 * 于是那条真实见过的模拟器路径反而绕过了校验。
 */
const BARE_PROXY_HOST_PATTERN =
  /^(?:[^\s/@\\]+@)?(?:\[[0-9A-Fa-f:]+\]|[A-Za-z0-9._-]+)(?::\d{1,5})?$/

/**
 * 日志里遮蔽代理地址中的凭据。
 *
 * `http://user:pass@host:port` 是合法写法，而 `frontend.log` 会被用户直接贴进 issue。
 */
function maskProxyCredentials(address: string): string {
  return address.replace(/:\/\/[^/@]*@/, '://***@')
}

/**
 * 读取并校验用户配置的出站代理地址（设置页「网络代理」，`Update.ProxyAddress`）。
 *
 * **必须严格校验**：这个字段在界面上没有任何约束，真机上见过用户把模拟器安装路径
 * （`D:\虚拟C盘\MuMuPlayer-12.0\nx_main`）填进去。把这种值原样导出成 `HTTPS_PROXY`
 * 会让 Runtime 一条网络路都走不通，比不设代理更糟，所以解析不出合法 URL、协议不在
 * 白名单里、或者没有主机名的，一律记 warn 后当作没配。
 *
 * **裸的 `主机[:端口]` 补 `http://`**，与后端同一字段的消费者对齐（`app/core/config.py`
 * 的 `GlobalConfig.proxy` 一直这么做）。否则 `127.0.0.1:7890` 这种写法后端认、这里不认，
 * 用户会看到「更新检查走了代理，Runtime 却还在裸连」——正是本函数要消灭的现象。
 * 但只对 `BARE_PROXY_HOST_PATTERN` 匹配的输入补，不像后端那样无脑加前缀。
 * 后端还放行 `socks4://`，而 Go 的 `ProxyFromEnvironment` 不支持，这里仍然拒绝。
 *
 * 返回可直接导出的地址字符串；没配或不合法时返回 null。
 */
function readProxyAddress(config: BackendConfigShape): string | null {
  const raw = config.Update?.ProxyAddress
  if (typeof raw !== 'string') return null

  const trimmed = raw.trim()
  if (trimmed.length === 0) return null

  const needsScheme = !PROXY_SCHEME_PATTERN.test(trimmed) && BARE_PROXY_HOST_PATTERN.test(trimmed)
  const normalized = needsScheme ? `http://${trimmed}` : trimmed
  const masked = maskProxyCredentials(normalized)

  let parsed: URL
  try {
    parsed = new URL(normalized)
  } catch {
    logger.warn(`代理地址不是合法 URL，已忽略: ${masked}`)
    return null
  }
  if (!ALLOWED_PROXY_PROTOCOLS.has(parsed.protocol)) {
    logger.warn(`代理地址协议 ${parsed.protocol} 不受支持，已忽略: ${masked}`)
    return null
  }
  if (parsed.hostname.length === 0) {
    logger.warn(`代理地址缺少主机名，已忽略: ${masked}`)
    return null
  }
  // 导出用户写的那串（仅补协议），不用 `URL.toString()`：它会加上没人需要的末尾斜杠，
  // 还会把凭据重新编码，反而与用户在设置页看到的值对不上。
  return normalized
}

/**
 * 构建传给 `RuntimeClient` 的环境变量覆盖。
 *
 * @param dataRoot 用户数据根，`config/Config.json` 所在处。
 * @param launchMode 本次启动链路；`development` 时追加 `AUTO_MAS_ENV=development`，其它模式
 *   （含未指定）不碰该变量。
 *
 * 关闭遥测时含 `AUTO_MAS_TELEMETRY: 'disabled'`；开启时不含该键。什么都不需要设时返回空对象。
 *
 * 用户配了合法代理时另含 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`：Runtime 的 go-git
 * 与镜像下载器用的都是 `http.DefaultTransport.Clone()`，本来就认这两个变量，只是此前
 * 没有人设过——国内用户配了代理也照样裸连 github.com，受管工作区首次克隆在 cnb 之后
 * 落到 github 兜底时必挂。
 *
 * **已知副作用**：Runtime 会把自己的环境原样交给 `uv run` 再交给后端
 * （`internal/uv/runner.go` 的 `buildEnvironment` 整份复制 `os.Environ()`，只过滤
 * `UV_*` 与几个 `AUTO_MAS_*`），所以这三个变量会一路漏到 uv 的依赖下载、后端的
 * httpx/requests，以及后端再拉起的脚本子进程。后端此前只在更新检查里显式用代理
 * （大多数客户端显式传 `Config.proxy`，受影响的是没显式传的那些），之后会跟着走。
 * 对「特意配了代理」的用户这多半正是所求，但这是一次行为扩大，`NO_PROXY` 因此是必需项。
 * 彻底的做法是 Runtime 侧加 `--proxy` 只作用于自己的出站，那需要 Runtime 单独发版。
 */
export function buildRuntimeEnv(
  dataRoot: string,
  launchMode?: RuntimeLaunchMode
): NodeJS.ProcessEnv {
  const config = readBackendConfig(dataRoot)
  const env: NodeJS.ProcessEnv = {}
  if (!isTelemetryEnabled(config)) {
    env[RUNTIME_TELEMETRY_ENV] = 'disabled'
  }
  if (launchMode === 'development') {
    env[RUNTIME_APP_ENV] = 'development'
  }
  const proxy = readProxyAddress(config)
  if (proxy) {
    env[RUNTIME_HTTP_PROXY_ENV] = proxy
    env[RUNTIME_HTTPS_PROXY_ENV] = proxy
    env[RUNTIME_NO_PROXY_ENV] = LOCAL_NO_PROXY
    logger.info(`已向 Runtime 透传出站代理: ${maskProxyCredentials(proxy)}`)
  }
  return env
}
