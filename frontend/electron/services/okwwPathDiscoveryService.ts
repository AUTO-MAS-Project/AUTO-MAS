import { execFile } from 'child_process'
import { promises as fs } from 'fs'
import path from 'path'

export type PathDiscoverySource = 'uninstall-registry' | 'kuro-launcher-registry' | 'wegame'

export type WutheringWavesChannel = 'China' | 'Global' | 'WeGame'

export interface PathDiscoveryResult {
  success: boolean
  path?: string
  source?: PathDiscoverySource
  channel?: WutheringWavesChannel
  error?: string
}

interface UninstallRegistryEntry {
  keyPath: string
  displayName: string | null
  publisher: string | null
  installLocation: string | null
  displayIcon: string | null
  uninstallString: string | null
}

interface KuroLauncherRegistryEntry {
  keyPath: string
  installPath: string | null
}

interface RegistrySnapshot {
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
const WEGAME_LAUNCHER_EXECUTABLES = ['wegame.exe', 'WeGame.exe']

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

function isWeGameEntry(entry: UninstallRegistryEntry): boolean {
  return normalizedIdentity(entry.keyPath, entry.displayName, entry.publisher).includes('wegame')
}

async function isFile(filePath: string): Promise<boolean> {
  try {
    return (await fs.stat(filePath)).isFile()
  } catch {
    return false
  }
}

async function isValidOkwwRoot(rootPath: string): Promise<boolean> {
  const sentinels = OKWW_RELATIVE_SENTINELS.map(relativePath =>
    path.win32.join(rootPath, relativePath)
  )
  return (await Promise.all(sentinels.map(isFile))).every(Boolean)
}

function channelFromLauncherKey(keyPath: string): WutheringWavesChannel | undefined {
  const normalized = keyPath.toLowerCase()
  if (normalized.includes('g152')) return 'China'
  if (normalized.includes('g153')) return 'Global'
  return undefined
}

function runRegistryQuery(): Promise<RegistrySnapshot> {
  const encodedCommand = Buffer.from(POWERSHELL_REGISTRY_QUERY, 'utf16le').toString('base64')

  return new Promise((resolve, reject) => {
    execFile(
      'powershell.exe',
      ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encodedCommand],
      { encoding: 'utf8', windowsHide: true, timeout: 15_000, maxBuffer: 5 * 1024 * 1024 },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error(stderr.trim() || error.message))
          return
        }
        try {
          resolve(parseRegistrySnapshot(stdout))
        } catch (parseError) {
          reject(parseError)
        }
      }
    )
  })
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
  for (const entry of matchingEntries) {
    for (const candidateRoot of uninstallEntryRoots(entry)) {
      if (await isValidOkwwRoot(candidateRoot)) {
        return {
          success: true,
          path: path.win32.normalize(candidateRoot),
          source: 'uninstall-registry',
        }
      }
    }
  }

  return {
    success: false,
    error: matchingEntries.length
      ? '已找到 ok-ww 卸载信息，但安装目录中的文件不完整，请重新安装或手动选择目录'
      : '未从 Windows 卸载信息中找到有效的 ok-ww 安装目录',
  }
}

async function discoverOfficialLauncher(
  launchers: KuroLauncherRegistryEntry[]
): Promise<PathDiscoveryResult | null> {
  for (const launcher of launchers) {
    for (const launcherRoot of rootsFromRegistryPath(launcher.installPath, 1)) {
      const launcherPath = path.win32.join(launcherRoot, OFFICIAL_LAUNCHER_EXECUTABLE)
      if (!(await isFile(launcherPath))) continue
      return {
        success: true,
        path: launcherPath,
        source: 'kuro-launcher-registry',
        channel: channelFromLauncherKey(launcher.keyPath),
      }
    }
  }
  return null
}

function weGameLauncherCandidates(entry: UninstallRegistryEntry): string[] {
  const directExecutables = [entry.installLocation, entry.displayIcon, entry.uninstallString]
    .map(parseRegistryPath)
    .filter((candidate): candidate is string => candidate !== null)
    .filter(candidate => path.win32.basename(candidate).toLowerCase() === 'wegame.exe')
  const rootExecutables = uninstallEntryRoots(entry, 3).flatMap(root =>
    WEGAME_LAUNCHER_EXECUTABLES.map(executable => path.win32.join(root, executable))
  )
  return uniquePaths([...directExecutables, ...rootExecutables])
}

async function discoverWeGameLauncher(
  uninstallEntries: UninstallRegistryEntry[]
): Promise<PathDiscoveryResult | null> {
  for (const entry of uninstallEntries.filter(isWeGameEntry)) {
    for (const launcherPath of weGameLauncherCandidates(entry)) {
      if (!(await isFile(launcherPath))) continue
      return {
        success: true,
        path: launcherPath,
        source: 'wegame',
        channel: 'WeGame',
      }
    }
  }
  return null
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

  const officialResult = await discoverOfficialLauncher(snapshot.kuroLaunchers)
  if (officialResult) return officialResult

  const weGameResult = await discoverWeGameLauncher(snapshot.uninstallEntries)
  if (weGameResult) return weGameResult

  const hasLauncherEvidence =
    snapshot.kuroLaunchers.length > 0 || snapshot.uninstallEntries.some(isWeGameEntry)
  return {
    success: false,
    error: hasLauncherEvidence
      ? '已找到鸣潮启动器信息，但启动器程序不存在，请重新安装或手动选择目录'
      : '未检测到鸣潮官方启动器或 WeGame，请先安装启动器，或使用“选择目录”手动导入',
  }
}
