import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { session } from 'electron'
import AdmZip from 'adm-zip'
import { parse } from 'smol-toml'
import type {
  AppUpdateCheck,
  AppUpdateSettings,
  AppUpdateSnapshot,
  AppUpdateEvent,
} from './appUpdateTypes'
import type { CoreUpgradePrecheckOut } from './backendDownloadService'
import { compareVersions } from './updateVersion'
import {
  backendRequest,
  downloadAndCopy,
  DownloadWriterUnconfirmed,
} from './backendDownloadService'
import type { BackendService } from './backendService'

type ChangelogData = Record<string, Record<string, string[]>>

const VERSION = /^v?\d+\.\d+\.\d+(?:-beta\.\d+)?$/
export function normalizeAppVersion(value: string): string {
  // 校验正式或 beta 应用版本号，并统一补齐 v 前缀用于发行资源定位。
  if (!VERSION.test(value)) throw new Error('无效的应用版本号')
  return value.startsWith('v') ? value : `v${value}`
}
export function parseUpdateNotes(value: unknown, current: string): ChangelogData {
  // 读取公告首行的结构化更新日志，只保留高于当前版本且内容有效的条目，并按版本倒序返回。
  if (typeof value !== 'string') return {}
  try {
    const parsed: unknown = JSON.parse(
      value.split(/\r?\n/)[0].replace(/^<!--\s*(.*?)\s*-->$/, '$1')
    )
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(
          ([version, section]) =>
            /* 筛选合法版本及分类文本列表，排除当前版本以前和结构异常的公告条目。 */ VERSION.test(
              version
            ) &&
            compareVersions(version, current) > 0 &&
            section &&
            typeof section === 'object' &&
            !Array.isArray(section) &&
            Object.values(section).every(
              notes =>
                /* 确认某个公告分类是仅包含文本的列表。 */ Array.isArray(notes) &&
                notes.every(
                  note =>
                    /* 确认公告单条内容为文本，避免无效结构进入界面。 */ typeof note === 'string'
                )
            )
        )
        .sort(([left], [right]) =>
          /* 按版本从新到旧排列筛选后的公告段落。 */ compareVersions(right, left)
        )
    )
  } catch {
    return {}
  }
}

async function queryRelease(input: AppUpdateSettings): Promise<Record<string, unknown>> {
  // 按当前更新来源、渠道和凭据查询发行服务，校验响应并返回发行数据。
  const url = new URL('https://mirrorchyan.com/api/resources/AUTO_MAS/latest')
  const settings = input.settings
  for (const [key, value] of Object.entries({
    user_agent: 'AutoMasGui',
    os: 'win',
    arch: 'x64',
    current_version: input.currentVersion,
    cdk: settings.Source === 'MirrorChyan' ? (settings.MirrorChyanCDK ?? '') : '',
    channel: settings.Channel ?? 'stable',
  }))
    url.searchParams.set(key, value)
  const network = session.fromPartition(`app-update:${randomUUID()}`)
  if (settings.ProxyAddress) await network.setProxy({ proxyRules: settings.ProxyAddress })
  const response = await network.fetch(url.toString(), { signal: AbortSignal.timeout(15_000) })
  const payload = (await response.json()) as {
    code?: unknown
    data?: Record<string, unknown>
    msg?: unknown
  }
  if (!response.ok || payload.code !== 0 || !payload.data)
    throw new Error(`查询应用发行版本失败 (${response.status}, ${String(payload.code)})`)
  return payload.data
}

let checkCache: { key: string; response: AppUpdateCheck; checkedAt: number } | null = null

export async function checkAppUpdate(input: AppUpdateSettings): Promise<AppUpdateCheck> {
  // 复用相同设置下的短期检查缓存，或查询发行版本、比较新旧并整理可用版本与公告。
  const key = createHash('sha256')
    .update(JSON.stringify([input.currentVersion, input.settings]))
    .digest('hex')
  if (!input.forceCheck && checkCache?.key === key && Date.now() - checkCache.checkedAt < 3_600_000)
    return structuredClone(checkCache.response)
  const data = await queryRelease(input)
  if (typeof data.version_name !== 'string') throw new Error('发行版本信息不完整')
  const latest = normalizeAppVersion(data.version_name)
  const available = compareVersions(latest, input.currentVersion) > 0
  const response = {
    code: 200,
    message: '',
    if_need_update: available,
    latest_version: available ? latest : input.currentVersion,
    update_info: available ? parseUpdateNotes(data.release_note, input.currentVersion) : {},
  }
  checkCache = { key, response, checkedAt: Date.now() }
  return structuredClone(response)
}

export async function precheckAppVersion(
  baseUrl: string,
  version: string,
  commit?: string
): Promise<void> {
  // 读取目标版本项目依赖并调用后端插件兼容性预检，存在冲突时阻止本次前端更新流程。
  const revision = commit && /^[a-f0-9]{40}$/i.test(commit) ? commit : normalizeAppVersion(version)
  const settings = await backendRequest<{
    data: { Update: { ProxyAddress?: string | null; Source?: string | null } }
  }>(baseUrl, '/api/setting/get', {})
  const network = session.fromPartition(`app-update-precheck:${randomUUID()}`)
  if (settings.data.Update.ProxyAddress)
    await network.setProxy({ proxyRules: settings.data.Update.ProxyAddress })
  const expectedPythonVersion = normalizeAppVersion(version)
    .slice(1)
    .replace(/-beta\.(\d+)$/, 'b$1')
  const sources = [
    `https://cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/git/raw/${revision}/pyproject.toml`,
    `https://raw.githubusercontent.com/AUTO-MAS-Project/AUTO-MAS/${revision}/pyproject.toml`,
  ]
  if (settings.data.Update.Source === 'GitHub') sources.reverse()
  let dependencies: string[] | undefined
  let lastError: unknown
  for (const url of sources) {
    try {
      const response = await network.fetch(url, { signal: AbortSignal.timeout(20_000) })
      if (!response.ok) throw new Error(`读取目标版本依赖失败 (${response.status})`)
      const document = parse(await response.text())
      const project = document.project as { dependencies?: unknown; version?: unknown } | undefined
      if (
        !project ||
        project.version !== expectedPythonVersion ||
        !Array.isArray(project.dependencies) ||
        !project.dependencies.length ||
        !project.dependencies.every(
          item =>
            /* 校验目标项目依赖列表的每个条目都是可交给后端解析的字符串。 */ typeof item ===
            'string'
        )
      )
        throw new Error('目标版本依赖声明无效')
      dependencies = project.dependencies
      break
    } catch (error) {
      lastError = error
    }
  }
  if (!dependencies) throw lastError ?? new Error('无法读取目标版本依赖')
  const result = await backendRequest<CoreUpgradePrecheckOut>(baseUrl, '/api/update/precheck', {
    version,
    dependencies,
  })
  if (!result.compatible)
    throw new Error(
      (result.conflicts ?? [])
        .map(item => /* 提取后端预检冲突消息，供前端组合成更新阻断原因。 */ item.message)
        .join('\n') || '插件与目标版本不兼容'
    )
}

const initial = (): AppUpdateSnapshot => /* 创建独立的空更新快照，作为更新服务初始状态。 */ ({
  status: 'idle',
  version: null,
  source: null,
  downloaded_size: 0,
  file_size: 0,
  speed: 0,
  file: null,
  message: null,
})
export class AppUpdateService {
  snapshot = initial()
  private abort: AbortController | null = null
  private running: Promise<void> | null = null
  private input: AppUpdateSettings | null = null
  private downloader: 'builtin' | 'fluxdown' | undefined
  private directory: string | null = null
  constructor(
    private root: string,
    private backendUrl: () => string,
    private publish: (event: AppUpdateEvent) => void
  ) {
    // 绑定应用根目录、后端地址提供方和更新事件发布回调。
  }
  private emit(type: AppUpdateEvent['type']): void {
    // 复制当前更新快照并发布指定类型事件，避免外部修改服务内部状态。
    this.publish({ type, snapshot: { ...this.snapshot } })
  }
  async start(
    version: string,
    input: AppUpdateSettings,
    downloader?: 'builtin' | 'fluxdown'
  ): Promise<void> {
    // 拒绝并行更新，冻结本次版本与设置，建立取消信号并等待下载流程结束。
    if (this.running) throw new Error('已有更新下载正在执行')
    const target = normalizeAppVersion(version)
    this.input = input
    this.downloader = downloader
    this.abort = new AbortController()
    this.snapshot = {
      ...initial(),
      status: 'downloading',
      version: target,
      source: input.settings.Source ?? 'CNB',
    }
    this.running = this.download(target, input, this.abort.signal).finally(() => {
      // 下载流程结束后释放在途任务和取消控制器，允许下一次更新操作。
      this.running = null
      this.abort = null
    })
    await this.running
  }
  private async download(
    version: string,
    input: AppUpdateSettings,
    signal: AbortSignal
  ): Promise<void> {
    // 先执行版本兼容预检，再按来源申请统一下载并复制更新包，更新进度与成功、取消或失败状态。
    try {
      await precheckAppVersion(this.backendUrl(), version)
      signal.throwIfAborted()
      const source = input.settings.Source ?? 'CNB'
      const asset = `AUTO-MAS-Setup-${version}-x64.zip`
      let url =
        source === 'GitHub'
          ? `https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/download/${version}/${asset}`
          : source === 'CNB'
            ? `https://cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/releases/download/${version}/${asset}`
            : `https://data.auto-mas.top/api/v1/files/auto-mas/Release/${version.includes('beta') ? 'beta' : 'stable'}/download`
      if (source === 'MirrorChyan') {
        const release = await queryRelease(input)
        if (
          typeof release.version_name !== 'string' ||
          normalizeAppVersion(release.version_name) !== version
        )
          throw new Error('所选更新版本已变化，请重新检查更新')
        if (typeof release.url === 'string' && release.url) url = release.url
      }
      this.directory = await fs.mkdtemp(path.join(await this.stageRoot(), 'package-'))
      const file = path.join(this.directory, asset)
      await downloadAndCopy(
        this.backendUrl(),
        { url, rid: version, downloader: this.downloader },
        file,
        {
          signal,
          progress: value => {
            // 将后端下载字节、总量和速度写入前端更新快照并发布进度事件。
            Object.assign(this.snapshot, {
              downloaded_size: value.downloaded ?? 0,
              file_size: value.total ?? 0,
              speed: value.speed ?? 0,
            })
            this.emit('progress')
          },
        }
      )
      this.snapshot = { ...this.snapshot, status: 'completed', file, speed: 0 }
      this.emit('completed')
    } catch (error) {
      const cancelled = signal.aborted && !(error instanceof DownloadWriterUnconfirmed)
      this.snapshot = {
        ...this.snapshot,
        status: cancelled ? 'cancelled' : 'failed',
        speed: 0,
        message: error instanceof Error ? error.message : String(error),
      }
      this.emit(cancelled ? 'cancelled' : 'failed')
      throw error
    }
  }
  private async stageRoot(): Promise<string> {
    // 创建并返回前端持有的更新暂存目录，供停止后端前复制安装材料。
    const root = path.join(this.root, '.frontend-updates')
    await fs.mkdir(root, { recursive: true })
    return root
  }
  async cancel(): Promise<void> {
    // 发出下载取消信号并等待收尾，下载器停写未确认时保留错误给调用方。
    this.abort?.abort()
    await this.running?.catch(error => {
      // 取消流程忽略普通下载失败，但继续传播无法确认停写的错误。
      if (error instanceof DownloadWriterUnconfirmed) throw error
    })
  }
  async switchToCnb(): Promise<void> {
    // 仅为 GitHub 在途版本执行来源切换，完成取消后保存 CNB 设置并重新申请下载。
    const version = this.snapshot.version
    const input = this.input
    if (!version || !input || this.snapshot.source !== 'GitHub')
      throw new Error('没有可切换的更新下载')
    await this.cancel()
    await backendRequest(this.backendUrl(), '/api/setting/update', {
      data: { Update: { Source: 'CNB' } },
    })
    await this.start(
      version,
      { ...input, settings: { ...input.settings, Source: 'CNB' as typeof input.settings.Source } },
      this.downloader
    )
  }
  async install(backend: BackendService): Promise<void> {
    // 再次预检目标版本，提取安装程序，停止所属后端并启动安装；启动失败时恢复后端。
    const { file, version } = this.snapshot
    if (!file || !version || this.snapshot.status !== 'completed' || !this.directory)
      throw new Error('请先完成更新下载')
    await precheckAppVersion(this.backendUrl(), version)
    const archive = new AdmZip(file)
    const entry = archive.getEntry('AUTO-MAS-Setup.exe')
    if (!entry || entry.isDirectory) throw new Error('更新包缺少安装程序')
    const installer = path.join(this.directory, 'AUTO-MAS-Setup.exe')
    await fs.writeFile(installer, entry.getData())
    const stopped = await backend.stopBackend()
    if (!stopped.success) throw new Error(stopped.error || '后端未能停止')
    try {
      const child = spawn(
        installer,
        [
          '/SP-',
          '/SILENT',
          '/NOCANCEL',
          '/FORCECLOSEAPPLICATIONS',
          '/LANG=Chinese',
          `/DIR=${this.root}`,
        ],
        { detached: true, windowsHide: true, stdio: 'ignore' }
      )
      await new Promise<void>((resolve, reject) => {
        // 等待安装器进程确认启动，启动失败则拒绝安装 Promise 进入恢复流程。
        child.once('spawn', resolve)
        child.once('error', reject)
      })
      child.unref()
    } catch (error) {
      await backend.startBackend()
      throw error
    }
  }
}
