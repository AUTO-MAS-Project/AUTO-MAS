import { execFile } from 'child_process'
import { promises as fs } from 'fs'
import path from 'path'
import { promisify } from 'util'

const execFileAsync = promisify(execFile)

export type WutheringWavesChannel = 'China' | 'Global'

export interface PathDiscoveryCandidate {
  path: string
  channel?: WutheringWavesChannel
}

export interface PathDiscoveryResult {
  success: boolean
  candidates?: PathDiscoveryCandidate[]
  path?: string
  channel?: WutheringWavesChannel
  error?: string
}

export interface UninstallRegistryEntry {
  keyPath: string
  displayName: string | null
  publisher: string | null
  installLocation: string | null
  displayIcon: string | null
  uninstallString: string | null
}

export interface KuroLauncherRegistryEntry {
  keyPath: string
  installPath: string | null
}

export interface RegistrySnapshot {
  uninstallEntries: UninstallRegistryEntry[]
  kuroLaunchers: KuroLauncherRegistryEntry[]
}

const POWERSHELL_REGISTRY_QUERY = String.raw`
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$uninstallEntries = @()
$uninstallRoots = @(
  'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
  'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
  'Registry::HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
  'Registry::HKEY_CURRENT_USER\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
)

foreach ($root in $uninstallRoots) {
  if (-not (Test-Path -LiteralPath $root)) { continue }
  foreach ($key in Get-ChildItem -LiteralPath $root) {
    $item = Get-ItemProperty -LiteralPath $key.PSPath
    $uninstallEntries += [pscustomobject]@{
      keyPath = [string]$key.Name
      displayName = if ($null -eq $item.DisplayName) { $null } else { [string]$item.DisplayName }
      publisher = if ($null -eq $item.Publisher) { $null } else { [string]$item.Publisher }
      installLocation = if ($null -eq $item.InstallLocation) { $null } else { [string]$item.InstallLocation }
      displayIcon = if ($null -eq $item.DisplayIcon) { $null } else { [string]$item.DisplayIcon }
      uninstallString = if ($null -eq $item.UninstallString) { $null } else { [string]$item.UninstallString }
    }
  }
}

$kuroLaunchers = @()
$kuroRoot = 'Registry::HKEY_CURRENT_USER\Software\kurogame\KRLauncher'
if (Test-Path -LiteralPath $kuroRoot) {
  foreach ($key in Get-ChildItem -LiteralPath $kuroRoot) {
    $item = Get-ItemProperty -LiteralPath $key.PSPath
    $kuroLaunchers += [pscustomobject]@{
      keyPath = [string]$key.Name
      installPath = if ($null -eq $item.SingleLauncherInstallPath) { $null } else { [string]$item.SingleLauncherInstallPath }
    }
  }
}

$result = [pscustomobject]@{
  uninstallEntries = @($uninstallEntries)
  kuroLaunchers = @($kuroLaunchers)
}

ConvertTo-Json -InputObject $result -Compress -Depth 5
`

const OKWW_RELATIVE_SENTINELS = ['ok-ww.exe', 'data/apps/ok-ww/app.json']
const OFFICIAL_LAUNCHER_EXECUTABLE = 'launcher.exe'

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  return value === null || value === undefined ? [] : [value]
}

export function parseRegistrySnapshot(output: string): RegistrySnapshot {
  const parsed = asObject(JSON.parse(output.replace(/^\uFEFF/, '').trim()))

  return {
    uninstallEntries: asArray(parsed.uninstallEntries).map(value => {
      const item = asObject(value)
      return {
        keyPath: asString(item.keyPath) || '',
        displayName: asString(item.displayName),
        publisher: asString(item.publisher),
        installLocation: asString(item.installLocation),
        displayIcon: asString(item.displayIcon),
        uninstallString: asString(item.uninstallString),
      }
    }),
    kuroLaunchers: asArray(parsed.kuroLaunchers).map(value => {
      const item = asObject(value)
      return {
        keyPath: asString(item.keyPath) || '',
        installPath: asString(item.installPath),
      }
    }),
  }
}

function expandEnvironmentVariables(value: string): string {
  return value.replace(/%([^%]+)%/g, (match, variableName: string) => {
    const key = Object.keys(process.env).find(
      candidate => candidate.toLowerCase() === variableName.toLowerCase()
    )
    return key ? process.env[key] || match : match
  })
}

export function parseRegistryPath(value: string | null): string | null {
  if (!value) return null

  const expanded = expandEnvironmentVariables(value.trim().replace(/^@/, ''))
  let candidate = expanded

  const quotedPath = expanded.match(/^"([^"]+)"/)
  const executablePath = expanded.match(/^(.+?\.exe)(?:\s|,|$)/i)
  if (quotedPath) {
    candidate = quotedPath[1]
  } else if (executablePath) {
    candidate = executablePath[1]
  } else {
    candidate = expanded
      .replace(/^"|"$/g, '')
      .replace(/,\s*-?\d+$/, '')
      .trim()
  }

  if (!path.win32.isAbsolute(candidate)) return null
  return path.win32.normalize(candidate)
}

function uniquePaths(paths: string[]): string[] {
  const seen = new Set<string>()
  return paths.filter(candidate => {
    const key = path.win32.normalize(candidate).toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function uniqueCandidates(candidates: PathDiscoveryCandidate[]): PathDiscoveryCandidate[] {
  const grouped = new Map<string, PathDiscoveryCandidate[]>()

  for (const candidate of candidates) {
    const normalizedPath = path.win32.normalize(candidate.path)
    const key = normalizedPath.toLowerCase()
    const group = grouped.get(key) || []
    group.push({ ...candidate, path: normalizedPath })
    grouped.set(key, group)
  }

  return [...grouped.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, group]) => {
      const sorted = [...group].sort(
        (left, right) =>
          left.path.localeCompare(right.path) ||
          (left.channel || '').localeCompare(right.channel || '')
      )
      const candidate = sorted[0]
      const channels = [...new Set(group.map(item => item.channel).filter(Boolean))]
      return {
        ...candidate,
        channel: channels.length === 1 ? channels[0] : undefined,
      }
    })
}

function successResult(candidates: PathDiscoveryCandidate[]): PathDiscoveryResult {
  const [candidate] = candidates
  return {
    success: true,
    candidates,
    path: candidate.path,
    channel: candidate.channel,
  }
}

function rootsFromRegistryPath(value: string | null, ancestorLimit: number): string[] {
  const parsed = parseRegistryPath(value)
  if (!parsed) return []

  const roots: string[] = []
  let current =
    path.win32.extname(parsed).toLowerCase() === '.exe' ? path.win32.dirname(parsed) : parsed
  for (let depth = 0; depth <= ancestorLimit; depth += 1) {
    roots.push(current)
    const parent = path.win32.dirname(current)
    if (parent === current) break
    current = parent
  }
  return roots
}

function uninstallEntryRoots(entry: UninstallRegistryEntry, ancestorLimit = 2): string[] {
  return uniquePaths([
    ...rootsFromRegistryPath(entry.installLocation, ancestorLimit),
    ...rootsFromRegistryPath(entry.displayIcon, ancestorLimit),
    ...rootsFromRegistryPath(entry.uninstallString, ancestorLimit),
  ])
}

function normalizedIdentity(...values: Array<string | null>): string {
  return values
    .join(' ')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
}

function isOkwwEntry(entry: UninstallRegistryEntry): boolean {
  return normalizedIdentity(entry.keyPath, entry.displayName, entry.publisher).includes('okww')
}

async function isFile(filePath: string): Promise<boolean> {
  try {
    return (await fs.stat(filePath)).isFile()
  } catch {
    return false
  }
}

async function isValidOkwwRoot(
  rootPath: string,
  fileExists: (filePath: string) => Promise<boolean> = isFile
): Promise<boolean> {
  const sentinels = OKWW_RELATIVE_SENTINELS.map(relativePath =>
    path.win32.join(rootPath, relativePath)
  )
  return (await Promise.all(sentinels.map(fileExists))).every(Boolean)
}

function channelFromLauncherKey(keyPath: string): WutheringWavesChannel | undefined {
  const normalized = keyPath.toLowerCase()
  if (normalized.includes('g152')) return 'China'
  if (normalized.includes('g153')) return 'Global'
  return undefined
}

async function runRegistryQuery(): Promise<RegistrySnapshot> {
  const encodedCommand = Buffer.from(POWERSHELL_REGISTRY_QUERY, 'utf16le').toString('base64')
  const { stdout } = await execFileAsync(
    'powershell.exe',
    ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encodedCommand],
    { encoding: 'utf8', windowsHide: true, timeout: 15_000, maxBuffer: 5 * 1024 * 1024 }
  )
  return parseRegistrySnapshot(stdout)
}

export async function discoverOkwwPath(): Promise<PathDiscoveryResult> {
  if (process.platform !== 'win32') {
    return { success: false, error: '一键导入仅支持 Windows 系统' }
  }

  let snapshot: RegistrySnapshot
  try {
    snapshot = await runRegistryQuery()
  } catch {
    return { success: false, error: '读取 Windows 卸载信息失败，请使用“选择目录”手动导入' }
  }

  const matchingEntries = snapshot.uninstallEntries.filter(isOkwwEntry)
  const candidates = await findOkwwCandidates(snapshot)
  if (candidates.length > 0) return successResult(candidates)

  return {
    success: false,
    error: matchingEntries.length
      ? '已找到 ok-ww 卸载信息，但安装目录中的文件不完整，请重新安装或手动选择目录'
      : '未从 Windows 卸载信息中找到有效的 ok-ww 安装目录',
  }
}

async function findOfficialLauncherCandidates(
  launchers: KuroLauncherRegistryEntry[],
  fileExists: (filePath: string) => Promise<boolean>
): Promise<PathDiscoveryCandidate[]> {
  const candidates: PathDiscoveryCandidate[] = []
  for (const launcher of launchers) {
    for (const launcherRoot of rootsFromRegistryPath(launcher.installPath, 1)) {
      const launcherPath = path.win32.join(launcherRoot, OFFICIAL_LAUNCHER_EXECUTABLE)
      if (!(await fileExists(launcherPath))) continue
      candidates.push({
        path: launcherPath,
        channel: channelFromLauncherKey(launcher.keyPath),
      })
    }
  }
  return candidates
}

export async function findOkwwCandidates(
  snapshot: RegistrySnapshot,
  fileExists: (filePath: string) => Promise<boolean> = isFile
): Promise<PathDiscoveryCandidate[]> {
  const roots = uniquePaths(
    snapshot.uninstallEntries.filter(isOkwwEntry).flatMap(entry => uninstallEntryRoots(entry))
  )
  const candidates = await Promise.all(
    roots.map(async rootPath =>
      (await isValidOkwwRoot(rootPath, fileExists))
        ? {
            path: rootPath,
          }
        : null
    )
  )
  return uniqueCandidates(
    candidates.filter((candidate): candidate is PathDiscoveryCandidate => candidate !== null)
  )
}

export async function findWutheringWavesCandidates(
  snapshot: RegistrySnapshot,
  fileExists: (filePath: string) => Promise<boolean> = isFile
): Promise<PathDiscoveryCandidate[]> {
  const candidates = await findOfficialLauncherCandidates(snapshot.kuroLaunchers, fileExists)
  return uniqueCandidates(candidates)
}

export async function discoverWutheringWavesPath(): Promise<PathDiscoveryResult> {
  if (process.platform !== 'win32') {
    return { success: false, error: '一键导入仅支持 Windows 系统' }
  }

  let snapshot: RegistrySnapshot
  try {
    snapshot = await runRegistryQuery()
  } catch {
    return { success: false, error: '读取 Windows 启动器信息失败，请使用“选择目录”手动导入' }
  }

  const candidates = await findWutheringWavesCandidates(snapshot)
  if (candidates.length > 0) return successResult(candidates)

  const hasLauncherEvidence = snapshot.kuroLaunchers.length > 0
  return {
    success: false,
    error: hasLauncherEvidence
      ? '已找到鸣潮启动器信息，但启动器程序不存在，请重新安装或手动选择目录'
      : '未检测到鸣潮官方启动器，请先安装启动器，或使用“选择目录”手动导入',
  }
}
