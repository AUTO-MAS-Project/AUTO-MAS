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
import { UpdateMaterial } from './updateStaging'

type ChangelogData = Record<string, Record<string, string[]>>

const SWITCH_SOURCE = Symbol('switch-source')

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

async function queryRelease(
  input: AppUpdateSettings,
  purpose: 'check' | 'download'
): Promise<Record<string, unknown>> {
  // 按当前更新来源、渠道和凭据查询发行服务，校验响应并返回发行数据。
  const url = new URL('https://mirrorchyan.com/api/resources/AUTO_MAS/latest')
  const settings = input.settings
  for (const [key, value] of Object.entries({
    user_agent: 'AutoMasGui',
    os: 'win',
    arch: 'x64',
    current_version: input.currentVersion,
    channel: settings.Channel ?? 'stable',
  }))
    url.searchParams.set(key, value)
  if (purpose === 'download' && settings.Source === 'MirrorChyan' && settings.MirrorChyanCDK) {
    url.searchParams.set('cdk', settings.MirrorChyanCDK)
  }
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
  const data = await queryRelease(input, 'check')
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
  commit?: string,
  signal?: AbortSignal
): Promise<void> {
  // 读取目标版本依赖并执行兼容性预检；取消信号贯通网络请求和后端解析进程。
  signal?.throwIfAborted()
  const revision = commit && /^[a-f0-9]{40}$/i.test(commit) ? commit : normalizeAppVersion(version)
  const settings = await backendRequest<{
    data: { Update: { ProxyAddress?: string | null; Source?: string | null } }
  }>(baseUrl, '/api/setting/get', {}, signal)
  const network = session.fromPartition(`app-update-precheck:${randomUUID()}`)
  if (settings.data.Update.ProxyAddress)
    await network.setProxy({ proxyRules: settings.data.Update.ProxyAddress })
  const expectedCoreVersion = normalizeAppVersion(version)
    .slice(1)
    .replace(/-beta\.(\d+)$/, 'b$1')
  const sources = [
    `https://cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/git/raw/${revision}/`,
    `https://raw.githubusercontent.com/AUTO-MAS-Project/AUTO-MAS/${revision}/`,
  ]
  if (settings.data.Update.Source === 'GitHub') sources.reverse()
  let target: { project: string; lockfile: string; python_version: string } | undefined
  let lastError: unknown
  for (const url of sources) {
    try {
      signal?.throwIfAborted()
      const timeout = AbortSignal.timeout(20_000)
      const responses = await Promise.all(
        ['pyproject.toml', 'uv.lock', '.python-version'].map(file =>
          network.fetch(`${url}${file}`, {
            signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
          })
        )
      )
      for (const response of responses)
        if (!response.ok) throw new Error(`读取目标版本依赖失败 (${response.status})`)
      const [projectText, lockfile, pythonText] = await Promise.all(
        responses.map(response => response.text())
      )
      const document = parse(projectText)
      const project = document.project as { dependencies?: unknown; version?: unknown } | undefined
      if (
        !project ||
        project.version !== expectedCoreVersion ||
        !Array.isArray(project.dependencies) ||
        !project.dependencies.length ||
        !project.dependencies.every(
          item =>
            /* 校验目标项目依赖列表的每个条目都是可交给后端解析的字符串。 */ typeof item ===
            'string'
        )
      )
        throw new Error('目标版本依赖声明无效')
      const python_version = pythonText.trim()
      if (!/^\d+\.\d+\.\d+$/.test(python_version)) throw new Error('目标 Python 版本声明无效')
      parse(lockfile)
      target = { project: projectText, lockfile, python_version }
      break
    } catch (error) {
      signal?.throwIfAborted()
      lastError = error
    }
  }
  signal?.throwIfAborted()
  if (!target) throw lastError ?? new Error('无法读取目标版本依赖')
  const result = await backendRequest<CoreUpgradePrecheckOut>(
    baseUrl,
    '/api/update/precheck',
    { version, ...target },
    signal
  )
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
  private downloadAbort: AbortController | null = null
  private running: Promise<void> | null = null
  private downloader: 'builtin' | 'fluxdown' | undefined
  private material: UpdateMaterial | null = null
  private installing = false
  private installation: Promise<void> | null = null
  private closing = false
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
    if (this.closing || this.running || this.installing) throw new Error('已有更新操作正在执行')
    const target = normalizeAppVersion(version)
    this.downloader = downloader
    this.abort = new AbortController()
    this.snapshot = {
      ...initial(),
      status: 'downloading',
      version: target,
      source: input.settings.Source ?? 'CNB',
    }
    const signal = this.abort.signal
    this.running = (async () => {
      // 旧会话的完整材料不再复用时先释放，再进入本次下载。
      await this.material?.dispose()
      this.material = null
      await this.download(target, input, signal)
    })().finally(() => {
      // 下载流程结束后释放在途任务和取消控制器，允许下一次更新操作。
      this.running = null
      this.abort = null
      this.downloadAbort = null
    })
    await this.running
  }
  private async download(
    version: string,
    input: AppUpdateSettings,
    signal: AbortSignal
  ): Promise<void> {
    // 同一次更新持有整体取消信号；换源只中断当前下载，收尾后在原流程内继续。
    let current = input
    try {
      while (true) {
        signal.throwIfAborted()
        const download = new AbortController()
        this.downloadAbort = download
        const currentSignal = AbortSignal.any([signal, download.signal])
        let material: UpdateMaterial | null = null
        let completed = false
        try {
          if (this.snapshot.status === 'switchingSource') {
            await backendRequest(
              this.backendUrl(),
              '/api/setting/update',
              {
                data: { Update: { Source: 'CNB' } },
              },
              currentSignal
            )
            current = { ...current, settings: { ...current.settings, Source: 'CNB' } }
            this.snapshot = { ...initial(), status: 'switchingSource', version, source: 'CNB' }
            this.emit('progress')
          }
          await precheckAppVersion(this.backendUrl(), version, undefined, currentSignal)
          currentSignal.throwIfAborted()
          const source = current.settings.Source ?? 'CNB'
          this.snapshot.status = 'downloading'
          this.emit('progress')
          const asset = `AUTO-MAS-Setup-${version}-x64.zip`
          let url =
            source === 'GitHub'
              ? `https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/download/${version}/${asset}`
              : source === 'CNB'
                ? `https://cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/releases/download/${version}/${asset}`
                : `https://data.auto-mas.top/api/v1/files/auto-mas/Release/${version.includes('beta') ? 'beta' : 'stable'}/download`
          if (source === 'MirrorChyan') {
            const release = await queryRelease(current, 'download')
            if (
              typeof release.version_name !== 'string' ||
              normalizeAppVersion(release.version_name) !== version
            )
              throw new Error('所选更新版本已变化，请重新检查更新')
            if (typeof release.url === 'string' && release.url) url = release.url
          }
          material = await UpdateMaterial.create(this.root, 'package', version)
          this.material = material
          const file = path.join(material.directory, asset)
          await downloadAndCopy(
            this.backendUrl(),
            { url, rid: version, downloader: this.downloader },
            `${file}.part`,
            {
              signal: currentSignal,
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
          currentSignal.throwIfAborted()
          await fs.rename(`${file}.part`, file)
          await material.setPhase('ready')
          currentSignal.throwIfAborted()
          completed = true
          this.snapshot = { ...this.snapshot, status: 'completed', file, speed: 0 }
          this.emit('completed')
          return
        } catch (error) {
          // 未确认停写时保持失败；用户取消优先，不能在旧源收尾后重新启动下载。
          if (error instanceof DownloadWriterUnconfirmed) throw error
          signal.throwIfAborted()
          if (download.signal.reason !== SWITCH_SOURCE) throw error
        } finally {
          // 复制与后端释放请求均已退出；失败、取消和换源只回收本次前端副本。
          if (!completed && material) {
            await material.dispose()
            if (this.material === material) this.material = null
          }
        }
      }
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
  async cancel(): Promise<void> {
    // 发出下载取消信号并等待收尾，下载器停写未确认时保留错误给调用方。
    this.abort?.abort()
    await this.running?.catch(error => {
      // 取消流程忽略普通下载失败，但继续传播无法确认停写的错误。
      if (error instanceof DownloadWriterUnconfirmed) throw error
    })
  }
  async switchToCnb(): Promise<void> {
    // 换源仅停止当前下载阶段；同一在途流程负责保存来源、重新预检及最终结果。
    if (
      !this.running ||
      this.snapshot.status !== 'downloading' ||
      this.snapshot.source !== 'GitHub'
    )
      throw new Error('没有可切换的更新下载')
    this.snapshot = { ...this.snapshot, status: 'switchingSource', speed: 0 }
    this.emit('progress')
    this.downloadAbort!.abort(SWITCH_SOURCE)
    await this.running
  }
  async install(backend: BackendService): Promise<void> {
    // 在第一次等待前取得安装资格，并跟踪整段安装准备供退出流程等待。
    if (this.closing || this.installing) throw new Error('安装已经开始，请等待安装器启动')
    this.installing = true
    this.installation = this.performInstall(backend)
    try {
      await this.installation
    } catch (error) {
      this.installing = false
      throw error
    } finally {
      this.installation = null
    }
  }
  private async performInstall(backend: BackendService): Promise<void> {
    // 再次预检目标版本，提取安装程序，停止所属后端并启动安装；启动失败时恢复后端。
    const { file, version } = this.snapshot
    const material = this.material
    if (!file || !version || this.snapshot.status !== 'completed' || !material)
      throw new Error('请先完成更新下载')
    try {
      try {
        await fs.access(file)
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
          this.snapshot = {
            ...this.snapshot,
            status: 'failed',
            file: null,
            message: '更新包已不存在，请重新下载',
          }
          this.emit('failed')
          throw new Error(this.snapshot.message!)
        }
        throw error
      }
      await precheckAppVersion(this.backendUrl(), version)
      if (this.closing) throw new Error('应用正在退出，已停止安装准备')
      const archive = new AdmZip(file)
      const entry = archive.getEntry('AUTO-MAS-Setup.exe')
      if (!entry || entry.isDirectory) throw new Error('更新包缺少安装程序')
      const installer = path.join(material.directory, 'AUTO-MAS-Setup.exe')
      await fs.writeFile(`${installer}.part`, entry.getData())
      await fs.rename(`${installer}.part`, installer)
      if (this.closing) throw new Error('应用正在退出，已停止安装准备')
      await material.setPhase('handoff')
      const stopped = await backend.stopBackend()
      if (!stopped.success) throw new Error(stopped.error || '后端未能停止')
      try {
        if (this.closing) throw new Error('应用正在退出，已停止安装准备')
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
        const exited = new Promise<void>(resolve => child.once('exit', () => resolve()))
        await new Promise<void>((resolve, reject) => {
          // 等待安装器进程确认启动，启动失败则拒绝安装 Promise 进入恢复流程。
          child.once('spawn', resolve)
          child.once('error', reject)
        })
        child.unref()
        await material.recordInstaller(child.pid!)
        // 交接记录写完后才允许清理，避免安装器很快退出时与身份落盘竞争。
        void exited.then(() => material.installerExited())
      } catch (error) {
        if (!this.closing) await backend.startBackend()
        throw error
      }
    } catch (error) {
      // 未成功交接时恢复可用归属，保留完整压缩包供本次会话重试。
      await material.setPhase('ready')
      await fs.rm(path.join(material.directory, 'AUTO-MAS-Setup.exe.part'), { force: true })
      throw error
    }
  }
  async shutdown(exiting = false): Promise<void> {
    // 先阻止新操作并等待下载和安装准备退出，再释放尚未交给安装器的材料。
    this.closing = true
    try {
      await this.cancel()
    } finally {
      await this.installation?.catch(() => {})
      await this.material?.dispose()
      // 停止初始化或后端也复用此入口，只有真正退出应用才持续拒绝新更新。
      this.closing = exiting
    }
  }
}
