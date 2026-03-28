import * as fs from 'fs'
import * as path from 'path'
import { spawn } from 'child_process'
import * as crypto from 'crypto'
import AdmZip = require('adm-zip')

import { SmartDownloader, ProgressCallback } from './downloadService'
import { loadBackendConfigFile, loadFrontendConfigFile } from './frontendConfigService'
import { getLogger } from './logger'

const logger = getLogger('应用更新服务')

type UpdateSource = 'GitHub' | 'MirrorChyan' | 'AutoSite'

interface UpdateSettings {
  source: UpdateSource
  channel: string
  mirrorChyanCDK: string
}

interface MirrorChyanLatestResponse {
  code: number
  msg?: string
  data?: {
    version_name?: string
    release_note?: string
    url?: string
    checksum?: {
      sha256?: string
    }
  }
}

export interface UpdateCheckOut {
  code: number
  status: 'success' | 'error'
  message: string
  if_need_update: boolean
  latest_version: string
  update_info: Record<string, string[]>
}

export interface OutBase {
  code: number
  status: 'success' | 'error'
  message: string
  data?: Record<string, unknown>
}

export interface AppUpdateStatus {
  isDownloading: boolean
  isInstalling: boolean
  lastCheckTime?: string
  remoteVersion?: string
}

export class AppUpdateService {
  private readonly appRoot: string
  private readonly downloader: SmartDownloader
  private isDownloading = false
  private isInstalling = false

  private lastCheckTime?: Date
  private remoteVersion?: string
  private updateInfoCache?: Record<string, string[]>
  private mirrorChyanDownloadUrl?: string
  private mirrorChyanSha256?: string

  constructor(appRoot: string) {
    this.appRoot = appRoot
    this.downloader = new SmartDownloader()
  }

  async checkUpdate(currentVersion: string, ifForce: boolean = false): Promise<UpdateCheckOut> {
    try {
      if (
        !ifForce &&
        this.remoteVersion &&
        this.updateInfoCache &&
        this.lastCheckTime &&
        Date.now() - this.lastCheckTime.getTime() < 4 * 60 * 60 * 1000
      ) {
        logger.info('四小时内已检查更新，使用缓存结果')
        return {
          code: 200,
          status: 'success',
          message: '使用缓存更新信息',
          if_need_update: this.compareVersion(this.remoteVersion, currentVersion) > 0,
          latest_version: this.remoteVersion,
          update_info: this.updateInfoCache,
        }
      }

      const settings = this.readUpdateSettings()
      const query = new URLSearchParams({
        user_agent: 'AutoMasGui',
        os: 'win',
        arch: 'x64',
        current_version: currentVersion,
        channel: settings.channel,
        cdk: settings.source === 'MirrorChyan' ? settings.mirrorChyanCDK : '',
      })

      const url = `https://mirrorchyan.com/api/resources/AUTO_MAS/latest?${query.toString()}`
      logger.info(`开始检查更新: ${url}`)

      const response = await fetch(url, { redirect: 'follow' })
      const payload = (await response.json()) as MirrorChyanLatestResponse

      if (!response.ok || payload.code !== 0 || !payload.data?.version_name) {
        const errMsg = payload.msg || `检查更新失败: HTTP ${response.status}`
        return {
          code: 500,
          status: 'error',
          message: errMsg,
          if_need_update: false,
          latest_version: currentVersion,
          update_info: {},
        }
      }

      const latestVersion = payload.data.version_name
      this.remoteVersion = latestVersion
      this.lastCheckTime = new Date()
      this.mirrorChyanDownloadUrl = payload.data.url
      this.mirrorChyanSha256 = payload.data.checksum?.sha256

      const needUpdate = this.compareVersion(latestVersion, currentVersion) > 0
      const updateInfo = needUpdate
        ? this.parseUpdateInfo(payload.data.release_note || '', currentVersion)
        : {}
      this.updateInfoCache = updateInfo

      return {
        code: 200,
        status: 'success',
        message: '检查更新成功',
        if_need_update: needUpdate,
        latest_version: needUpdate ? latestVersion : currentVersion,
        update_info: updateInfo,
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`检查更新失败: ${errorMsg}`)
      return {
        code: 500,
        status: 'error',
        message: errorMsg,
        if_need_update: false,
        latest_version: currentVersion,
        update_info: {},
      }
    }
  }

  async downloadUpdate(targetVersion: string, onProgress?: ProgressCallback): Promise<OutBase> {
    if (this.isDownloading) {
      return {
        code: 500,
        status: 'error',
        message: '已有更新任务在进行中, 请勿重复操作',
      }
    }

    this.isDownloading = true

    try {
      const settings = this.readUpdateSettings()
      const normalizedVersion = targetVersion?.trim() || this.remoteVersion

      if (!normalizedVersion) {
        return {
          code: 400,
          status: 'error',
          message: '未检测到可用的远程版本, 请先检查更新',
        }
      }

      const packagePath = path.join(this.appRoot, `UpdatePack_${normalizedVersion}.zip`)
      if (fs.existsSync(packagePath)) {
        logger.info(`更新包已存在: ${packagePath}`)
        return {
          code: 200,
          status: 'success',
          message: '更新包已存在',
          data: { path: packagePath },
        }
      }

      const downloadUrl = this.resolveDownloadUrl(settings.source, normalizedVersion)
      if (!downloadUrl) {
        return {
          code: 500,
          status: 'error',
          message: `未知的下载源: ${settings.source}, 请检查配置文件`,
        }
      }

      logger.info(`开始下载更新包: ${downloadUrl}`)

      const tempPath = path.join(this.appRoot, 'download.temp')
      if (fs.existsSync(tempPath)) {
        fs.unlinkSync(tempPath)
      }

      let lastError = ''
      const retryLimit = 3
      for (let attempt = 1; attempt <= retryLimit; attempt++) {
        const result = await this.downloader.download(downloadUrl, tempPath, onProgress)
        if (result.success) {
          fs.renameSync(tempPath, packagePath)

          if (settings.source === 'MirrorChyan' && this.mirrorChyanSha256) {
            const verifyOk = await this.verifySha256(packagePath, this.mirrorChyanSha256)
            if (!verifyOk) {
              fs.unlinkSync(packagePath)
              return {
                code: 500,
                status: 'error',
                message: '下载包校验失败: SHA256 不匹配',
              }
            }
          }

          return {
            code: 200,
            status: 'success',
            message: '下载完成',
            data: { path: packagePath },
          }
        }

        lastError = result.error || '下载失败'
        logger.warn(`下载失败，重试 ${attempt}/${retryLimit}: ${lastError}`)
      }

      if (fs.existsSync(tempPath)) {
        fs.unlinkSync(tempPath)
      }

      return {
        code: 500,
        status: 'error',
        message: `下载失败: ${lastError}`,
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`下载更新失败: ${errorMsg}`)
      return {
        code: 500,
        status: 'error',
        message: errorMsg,
      }
    } finally {
      this.isDownloading = false
    }
  }

  async installUpdate(): Promise<OutBase> {
    if (this.isInstalling) {
      return {
        code: 500,
        status: 'error',
        message: '已有更新任务在进行中, 请勿重复操作',
      }
    }

    this.isInstalling = true

    try {
      const candidates = fs
        .readdirSync(this.appRoot)
        .filter(name => /^UpdatePack_(.+)\.zip$/.test(name))

      if (candidates.length === 0) {
        return {
          code: 500,
          status: 'error',
          message: '未检测到更新包, 请先下载更新',
        }
      }

      candidates.sort((a, b) => {
        const va = a.replace(/^UpdatePack_/, '').replace(/\.zip$/, '')
        const vb = b.replace(/^UpdatePack_/, '').replace(/\.zip$/, '')
        return this.compareVersion(vb, va)
      })

      const packageName = candidates[0]
      const packagePath = path.join(this.appRoot, packageName)
      logger.info(`开始解压更新包: ${packagePath}`)

      const zip = new AdmZip(packagePath)
      zip.extractAllTo(this.appRoot, true)

      const changesJsonPath = path.join(this.appRoot, 'changes.json')
      if (fs.existsSync(changesJsonPath)) {
        fs.unlinkSync(changesJsonPath)
      }

      for (const pack of candidates) {
        const p = path.join(this.appRoot, pack)
        if (fs.existsSync(p)) {
          fs.unlinkSync(p)
        }
      }

      const installerPath = path.join(this.appRoot, 'AUTO-MAS-Setup.exe')
      if (!fs.existsSync(installerPath)) {
        return {
          code: 500,
          status: 'error',
          message: `未找到安装程序: ${installerPath}`,
        }
      }

      spawn(
        installerPath,
        [
          '/SP-',
          '/SILENT',
          '/NOCANCEL',
          '/FORCECLOSEAPPLICATIONS',
          '/LANG=Chinese',
          `/DIR=${this.appRoot}`,
        ],
        {
          detached: true,
          stdio: 'ignore',
          windowsHide: true,
        }
      ).unref()

      logger.info('更新安装程序已启动')
      return {
        code: 200,
        status: 'success',
        message: '安装程序已启动',
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`安装更新失败: ${errorMsg}`)
      return {
        code: 500,
        status: 'error',
        message: errorMsg,
      }
    } finally {
      this.isInstalling = false
    }
  }

  getStatus(): AppUpdateStatus {
    return {
      isDownloading: this.isDownloading,
      isInstalling: this.isInstalling,
      lastCheckTime: this.lastCheckTime?.toISOString(),
      remoteVersion: this.remoteVersion,
    }
  }

  private resolveDownloadUrl(source: UpdateSource, remoteVersion: string): string | null {
    if (source === 'GitHub') {
      return `https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/download/${remoteVersion}/AUTO-MAS-Lite-Setup-${remoteVersion}-x64.zip`
    }

    if (source === 'MirrorChyan') {
      if (this.mirrorChyanDownloadUrl) {
        return this.mirrorChyanDownloadUrl
      }
      logger.warn('MirrorChyan 未返回下载链接，使用自建下载站')
      return `https://download.auto-mas.top/d/AUTO-MAS/AUTO-MAS-Lite-Setup-${remoteVersion}-x64.zip`
    }

    if (source === 'AutoSite') {
      return `https://download.auto-mas.top/d/AUTO-MAS/AUTO-MAS-Lite-Setup-${remoteVersion}-x64.zip`
    }

    return null
  }

  private readUpdateSettings(): UpdateSettings {
    let source: UpdateSource = 'GitHub'
    let channel = 'stable'
    let mirrorChyanCDK = ''

    try {
      const frontendConfig = loadFrontendConfigFile(this.appRoot)
      if (frontendConfig) {
        const frontendUpdateSettings = (frontendConfig.Update || {}) as Record<string, any>
        if (
          typeof frontendUpdateSettings.Source === 'string' &&
          ['GitHub', 'MirrorChyan', 'AutoSite'].includes(frontendUpdateSettings.Source)
        ) {
          source = frontendUpdateSettings.Source as UpdateSource
        }
        if (
          typeof frontendUpdateSettings.Channel === 'string' &&
          frontendUpdateSettings.Channel.trim()
        ) {
          channel = frontendUpdateSettings.Channel.trim()
        }
        if (typeof frontendUpdateSettings.MirrorChyanCDK === 'string') {
          mirrorChyanCDK = frontendUpdateSettings.MirrorChyanCDK.trim()
        }
      }
    } catch (error) {
      logger.warn(`读取前端配置失败，使用默认更新设置: ${error}`)
    }

    try {
      const backendConfig = loadBackendConfigFile(this.appRoot)
      if (backendConfig) {
        const backendUpdateSettings = (backendConfig.Update || {}) as Record<string, any>
        if (
          typeof backendUpdateSettings.Source === 'string' &&
          ['GitHub', 'MirrorChyan', 'AutoSite'].includes(backendUpdateSettings.Source)
        ) {
          source = backendUpdateSettings.Source as UpdateSource
        }
        if (
          typeof backendUpdateSettings.Channel === 'string' &&
          backendUpdateSettings.Channel.trim()
        ) {
          channel = backendUpdateSettings.Channel.trim()
        }
        if (
          typeof backendUpdateSettings.MirrorChyanCDK === 'string' &&
          backendUpdateSettings.MirrorChyanCDK.trim()
        ) {
          mirrorChyanCDK = backendUpdateSettings.MirrorChyanCDK.trim()
        }
      }
    } catch (error) {
      logger.warn(`读取后端配置失败，忽略后端更新设置覆盖: ${error}`)
    }

    return {
      source,
      channel,
      mirrorChyanCDK,
    }
  }

  private parseUpdateInfo(releaseNote: string, currentVersion: string): Record<string, string[]> {
    try {
      const firstLine = releaseNote.split('\n')[0]?.trim() || ''
      const commentBody = firstLine.replace(/^<!--\s*/, '').replace(/\s*-->$/, '')
      if (!commentBody) {
        return {}
      }

      const versionInfo = JSON.parse(commentBody) as Record<string, Record<string, string[]>>
      const merged: Record<string, string[]> = {}

      for (const [versionKey, payload] of Object.entries(versionInfo)) {
        if (this.compareVersion(versionKey, currentVersion) <= 0) {
          continue
        }

        for (const [category, items] of Object.entries(payload)) {
          if (!merged[category]) {
            merged[category] = []
          }
          merged[category].push(...items)
        }
      }

      return merged
    } catch (error) {
      logger.warn(`解析更新说明失败，返回空更新内容: ${error}`)
      return {}
    }
  }

  private parseVersionParts(version: string): {
    releaseParts: number[]
    prereleaseParts: Array<number | string>
  } {
    const normalizedVersion = version.replace(/^v/i, '')
    const [releasePart, prereleasePart = ''] = normalizedVersion.split('-', 2)

    return {
      releaseParts: releasePart
        .split('.')
        .filter(Boolean)
        .map(part => Number.parseInt(part, 10) || 0),
      prereleaseParts: prereleasePart
        .split('.')
        .filter(Boolean)
        .map(part => (/^\d+$/.test(part) ? Number(part) : part.toLowerCase())),
    }
  }

  private compareVersion(a: string, b: string): number {
    const versionA = this.parseVersionParts(a)
    const versionB = this.parseVersionParts(b)
    const releaseLength = Math.max(versionA.releaseParts.length, versionB.releaseParts.length)

    for (let i = 0; i < releaseLength; i++) {
      const left = versionA.releaseParts[i] ?? 0
      const right = versionB.releaseParts[i] ?? 0
      if (left !== right) {
        return left > right ? 1 : -1
      }
    }

    const hasPrereleaseA = versionA.prereleaseParts.length > 0
    const hasPrereleaseB = versionB.prereleaseParts.length > 0

    // 正式版优先级高于同版本号的预发布版。
    if (!hasPrereleaseA && !hasPrereleaseB) {
      return 0
    }
    if (!hasPrereleaseA) {
      return 1
    }
    if (!hasPrereleaseB) {
      return -1
    }

    const prereleaseLength = Math.max(
      versionA.prereleaseParts.length,
      versionB.prereleaseParts.length
    )

    for (let i = 0; i < prereleaseLength; i++) {
      const left = versionA.prereleaseParts[i]
      const right = versionB.prereleaseParts[i]

      if (left === undefined) {
        return -1
      }
      if (right === undefined) {
        return 1
      }
      if (left === right) {
        continue
      }

      if (typeof left === 'number' && typeof right === 'number') {
        return left > right ? 1 : -1
      }
      if (typeof left === 'number') {
        return -1
      }
      if (typeof right === 'number') {
        return 1
      }

      return left.localeCompare(right, undefined, {
        numeric: true,
        sensitivity: 'base',
      })
    }

    return 0
  }

  private async verifySha256(filePath: string, expectedHash: string): Promise<boolean> {
    const normalizedExpected = expectedHash.trim().toLowerCase()
    const hash = crypto.createHash('sha256')
    const stream = fs.createReadStream(filePath)

    return new Promise(resolve => {
      stream.on('data', chunk => hash.update(chunk))
      stream.on('end', () => {
        const actual = hash.digest('hex').toLowerCase()
        const ok = actual === normalizedExpected
        if (!ok) {
          logger.error(`SHA256 校验失败: expected=${normalizedExpected}, actual=${actual}`)
        }
        resolve(ok)
      })
      stream.on('error', error => {
        logger.error(`SHA256 校验读取失败: ${error}`)
        resolve(false)
      })
    })
  }
}
