import { execFile } from 'child_process'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

// 问题包里每个 MFW 脚本附一份「项目自带运行时」检查结果：M9A 这类项目的自带 Python 不带
// site-packages/maa/bin，原因只在 import maa 的最后一行（v5.6.0 现场日志全被截掉，只能让用户
// 手敲命令）。这里只读文件、跑一次 import，不改视图（不写字节码）。

// 与 app/task/MaaFW/tools/core/agent_env/env.py 同步：健康检查的探测语句与
// _build_project_python_probe_env 的判据（maa/bin 不在、项目自带库两份都在才指 MAAFW_BINARY_PATH）
const PROBE_STATEMENT = 'from maa.agent.agent_server import AgentServer'
const FRAMEWORK_DLL = 'MaaFramework.dll'
const AGENT_SERVER_DLL = 'MaaAgentServer.dll'
const IMPORT_TIMEOUT_MS = 15_000
const MAX_REASON_CHARS = 500
// 与 app/task/MaaFW/tools/core/runtime_pool/host_environment.py 的 ISOLATED_HOST_KEYS 里
// binding 相关的那几个同步；PYTHON* 一律不传
const ISOLATED_KEYS = new Set([
  'MAAFW_BINARY_PATH',
  'AUTO_MAS_MAAFW_BINDING_DIR',
  'AUTO_MAS_MAAFW_NATIVE_DIR',
])

export interface ProjectRuntimeSummary {
  /** 视图里的自带解释器（相对视图），没有为 null */
  python: string | null
  /** 自带解释器 site-packages 里的 maafw-*.dist-info 版本 */
  maafwBindings: string[]
  /** site-packages/maa/bin 在不在；找不到 maa 包为 null */
  maaBin: boolean | null
  /** 项目自带 MaaFramework 原生库目录（相对视图），没有为 null */
  nativeDir: string | null
  /** nativeDir 里 MaaFramework 内嵌的版本，读不出为 null */
  nativeVersion: string | null
  nativeHasAgentServer: boolean
  /** 检查时是否像后端那样把 MAAFW_BINARY_PATH 指到 nativeDir */
  checkUsedProjectNative: boolean
  /** 「通过」或失败原因（traceback 最后一行） */
  importMaa: string
}

function isDirectory(target: string): boolean {
  try {
    return fs.statSync(target).isDirectory()
  } catch {
    return false
  }
}

function isFile(target: string): boolean {
  try {
    return fs.statSync(target).isFile()
  } catch {
    return false
  }
}

// 与 app/task/MaaFW/tools/core/runner/environment.py 的 _RID_ARCHITECTURE_ALIASES /
// runtime_identifier_matches_host 同步：rid 最后一段是架构，其余是系统前缀（win10-x64 也算本机）
const RID_ARCHITECTURE_ALIASES: Record<string, string> = {
  x64: 'x64',
  amd64: 'x64',
  x86_64: 'x64',
  arm64: 'arm64',
  aarch64: 'arm64',
  x86: 'x86',
  i386: 'x86',
  i686: 'x86',
}

function hostArchitecture(): string {
  return { x64: 'x64', arm64: 'arm64', ia32: 'x86' }[process.arch as string] ?? process.arch
}

export function ridMatchesHost(rid: string): boolean {
  const lowered = rid.toLowerCase()
  const separator = lowered.lastIndexOf('-')
  if (separator < 0) {
    return false
  }
  const architecture = RID_ARCHITECTURE_ALIASES[lowered.slice(separator + 1)]
  return architecture === hostArchitecture() && lowered.slice(0, separator).startsWith('win')
}

// 与 app/task/MaaFW/tools/core/runner/environment.py 的 _MAAFW_DLL_VERSION_RE 同步
const DLL_VERSION_RE = /(?<![0-9A-Za-z.])v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)(?![0-9A-Za-z.])/g

/** 原生库里内嵌的版本串（如 5.14.0、5.13.0-beta.2）；不是恰好一个时为 null。 */
export function readNativeVersion(nativeDir: string): string | null {
  let text: string
  try {
    text = fs.readFileSync(path.join(nativeDir, FRAMEWORK_DLL)).toString('latin1')
  } catch {
    return null
  }
  const found = new Set(Array.from(text.matchAll(DLL_VERSION_RE), match => match[1]))
  return found.size === 1 ? [...found][0] : null
}

/** 比较 5.14.0 / 5.13.0-beta.2 这类版本：数字段逐位比，同号时正式版高于预发布。 */
export function compareNativeVersions(left: string, right: string): number {
  const split = (text: string): [number[], string] => {
    const [core, pre = ''] = text.split(/-(.*)/s)
    return [core.split('.').map(Number), pre]
  }
  const [leftCore, leftPre] = split(left)
  const [rightCore, rightPre] = split(right)
  for (let index = 0; index < 3; index += 1) {
    const diff = (leftCore[index] ?? 0) - (rightCore[index] ?? 0)
    if (diff) {
      return diff
    }
  }
  if (leftPre === rightPre) {
    return 0
  }
  if (!leftPre || !rightPre) {
    return leftPre ? -1 : 1
  }
  return leftPre.localeCompare(rightPre, undefined, { numeric: true })
}

/**
 * 后端 project_maafw_runtime_path 的已知布局部分：maafw/ 与 runtimes/<rid>/native（本机 rid 优先）
 * 里有好几份时取版本最高的，版本相同或读不出时按这个顺序取第一份。后端另有 runtimes/<rid> 本身、
 * 有界逐层搜索与跳过架构不符的库，这里不做：非标准布局下这份检查可能报失败而后端能过，
 * 看 nativeDir 是不是 null 就能分辨。
 */
function findNativeDir(viewDir: string): string | null {
  const candidates = [path.join(viewDir, 'maafw')]
  const runtimes = path.join(viewDir, 'runtimes')
  let rids: string[] = []
  try {
    rids = fs.readdirSync(runtimes).filter(name => isDirectory(path.join(runtimes, name)))
  } catch {
    rids = []
  }
  // 与后端 _project_runtime_rid_dirs 一致：本机能加载的 rid 在前，其余照名字顺序
  rids.sort(
    (left, right) =>
      Number(ridMatchesHost(right)) - Number(ridMatchesHost(left)) || left.localeCompare(right)
  )
  candidates.push(...rids.map(rid => path.join(runtimes, rid, 'native')))
  const present = candidates.filter(candidate => isFile(path.join(candidate, FRAMEWORK_DLL)))
  if (present.length <= 1) {
    return present[0] ?? null
  }
  let best = present[0]
  let bestVersion: string | null = null
  for (const candidate of present) {
    const version = readNativeVersion(candidate)
    if (version && (!bestVersion || compareNativeVersions(version, bestVersion) > 0)) {
      best = candidate
      bestVersion = version
    }
  }
  return best
}

function sitePackagesOf(pythonExe: string): string {
  return path.join(path.dirname(pythonExe), 'Lib', 'site-packages')
}

function maafwBindingsOf(sitePackages: string): string[] {
  try {
    return fs
      .readdirSync(sitePackages)
      .map(name => /^maafw-(.+)\.dist-info$/i.exec(name)?.[1])
      .filter((version): version is string => !!version)
      .sort()
  } catch {
    return []
  }
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 问题包清单不走通用脱敏：视图、安装目录、用户目录换成 <视图> / <安装目录> / <HOME>。
 * Python 的 OSError 用 repr 显示路径（反斜杠成对），三种写法都要认。
 */
export function redactPaths(text: string, viewDir: string): string {
  let result = text
  // 视图是 <安装目录>/data/mfw/<12hex>，先换最长的
  const installRoot = path.resolve(viewDir, '..', '..', '..')
  for (const [target, label] of [
    [viewDir, '<视图>'],
    [installRoot, '<安装目录>'],
    [os.homedir(), '<HOME>'],
  ]) {
    if (!target || path.parse(target).root === target) {
      continue
    }
    const variants = [target.replace(/\\/g, '\\\\'), target, target.replace(/\\/g, '/')]
    for (const variant of new Set(variants)) {
      result = result.replace(new RegExp(escapeRegExp(variant), 'gi'), label)
    }
  }
  return result
}

function lastLine(text: string): string {
  const lines = text.split(/\r?\n/).filter(line => line.trim())
  return lines.length ? lines[lines.length - 1].trim() : ''
}

function probeEnvironment(viewDir: string, nativeDir: string | null): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  for (const [key, value] of Object.entries(process.env)) {
    const upper = key.toUpperCase()
    if (upper.startsWith('PYTHON') || ISOLATED_KEYS.has(upper) || upper === 'VIRTUAL_ENV') {
      continue
    }
    env[key] = value
  }
  env.PYTHONPATH = viewDir
  env.PYTHONIOENCODING = 'utf-8'
  // 只读检查：不往视图里写字节码
  env.PYTHONDONTWRITEBYTECODE = '1'
  if (nativeDir) {
    env.MAAFW_BINARY_PATH = nativeDir
  }
  return env
}

function runImport(pythonExe: string, viewDir: string, env: NodeJS.ProcessEnv): Promise<string> {
  return new Promise(resolve => {
    execFile(
      pythonExe,
      ['-c', PROBE_STATEMENT],
      { cwd: viewDir, env, timeout: IMPORT_TIMEOUT_MS, windowsHide: true, encoding: 'utf8' },
      (error, stdout, stderr) => {
        if (!error) {
          resolve('通过')
          return
        }
        if (error.killed) {
          resolve(`失败：超过 ${IMPORT_TIMEOUT_MS / 1000}s 没有结束`)
          return
        }
        const reason = lastLine(String(stderr || stdout || '')) || error.message
        resolve(`失败：${reason.slice(-MAX_REASON_CHARS)}`)
      }
    )
  })
}

export async function probeProjectRuntime(viewDir: string): Promise<ProjectRuntimeSummary> {
  const pythonExe = path.join(viewDir, 'python', 'python.exe')
  const nativeDir = findNativeDir(viewDir)
  const nativeHasAgentServer = !!nativeDir && isFile(path.join(nativeDir, AGENT_SERVER_DLL))
  const summary: ProjectRuntimeSummary = {
    python: null,
    maafwBindings: [],
    maaBin: null,
    nativeDir: nativeDir ? path.relative(viewDir, nativeDir).replace(/\\/g, '/') : null,
    nativeVersion: nativeDir ? readNativeVersion(nativeDir) : null,
    nativeHasAgentServer,
    checkUsedProjectNative: false,
    importMaa: '未检查：视图里没有自带的 python/python.exe',
  }
  if (!isFile(pythonExe)) {
    return summary
  }
  const sitePackages = sitePackagesOf(pythonExe)
  summary.python = 'python/python.exe'
  summary.maafwBindings = maafwBindingsOf(sitePackages)
  if (isFile(path.join(sitePackages, 'maa', '__init__.py'))) {
    summary.maaBin = isDirectory(path.join(sitePackages, 'maa', 'bin'))
  }
  if (process.platform !== 'win32') {
    summary.importMaa = '未检查：不是 Windows'
    return summary
  }
  summary.checkUsedProjectNative = summary.maaBin === false && nativeHasAgentServer
  const env = probeEnvironment(viewDir, summary.checkUsedProjectNative ? nativeDir : null)
  summary.importMaa = redactPaths(await runImport(pythonExe, viewDir, env), viewDir)
  return summary
}
