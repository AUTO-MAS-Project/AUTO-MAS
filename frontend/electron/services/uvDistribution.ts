import * as fs from 'fs'
import * as path from 'path'
import type { MirrorSource } from './mirrorService'

export const UV_ARCHIVE_NAME = 'uv-x86_64-pc-windows-msvc.zip'
export const UV_BINARY_NAMES = ['uv.exe', 'uvx.exe', 'uvw.exe'] as const
export const UV_FALLBACK_VERSION = '0.11.33'
export const UV_FALLBACK_SHA256 = 'c253ce868ad48d29327b661452ce184c9e333e6d6f5bc8d6fcfbf4dd52b83442'
export const UV_LATEST_METADATA_URL = 'https://uv.agentsmirror.com/metadata/uv-latest.json'
export const UV_GITHUB_LATEST_API_URL = 'https://api.github.com/repos/astral-sh/uv/releases/latest'

interface UvDeploymentEntry {
  targetPath: string
  candidatePath: string
  backupPath: string
  backupCreated: boolean
  activated: boolean
}

export interface UvDeploymentFileSystem {
  constants: { COPYFILE_EXCL: number }
  copyFileSync(source: string, destination: string, mode: number): void
  existsSync(filePath: string): boolean
  renameSync(source: string, destination: string): void
  unlinkSync(filePath: string): void
  rmSync(filePath: string, options: { force: boolean }): void
}

function getGithubReleaseUrl(version: string): string {
  return `https://github.com/astral-sh/uv/releases/download/${version}/${UV_ARCHIVE_NAME}`
}

export function assertCompleteUvBinarySet(binaryNames: Iterable<string>): void {
  const available = new Set([...binaryNames].map(name => name.toLowerCase()))
  const missing = UV_BINARY_NAMES.filter(name => !available.has(name))
  if (missing.length > 0) {
    throw new Error(`uv ZIP 中缺少必需文件: ${missing.join(', ')}`)
  }
}

export function isUvVersionSupported(versionOutput: string): boolean {
  const currentMatch = versionOutput.trim().match(/^uv\s+(\d+)\.(\d+)\.(\d+)(?:\s|$)/)
  const minimumMatch = UV_FALLBACK_VERSION.match(/^(\d+)\.(\d+)\.(\d+)$/)

  if (!currentMatch || !minimumMatch) {
    return false
  }

  const current = currentMatch.slice(1, 4).map(Number)
  const minimum = minimumMatch.slice(1, 4).map(Number)

  for (let index = 0; index < current.length; index++) {
    if (current[index] !== minimum[index]) {
      return current[index] > minimum[index]
    }
  }

  return true
}

export function isUvVersionExact(versionOutput: string, expectedVersion: string): boolean {
  const match = versionOutput.trim().match(/^uv\s+(\d+\.\d+\.\d+)(?:\s|$)/)
  return match?.[1] === expectedVersion
}

/**
 * 为已解析出的 uv 版本创建下载源。
 *
 * 先解析 latest 为具体版本，再生成固定 URL，避免各镜像的 latest 同步时差。
 */
export function createUvMirrors(version: string = UV_FALLBACK_VERSION): MirrorSource[] {
  const githubReleaseUrl = getGithubReleaseUrl(version)

  return [
    {
      key: 'github_agentsmirror',
      name: 'uv-custom 公益镜像',
      url: `https://uv.agentsmirror.com/github/astral-sh/uv/releases/download/${version}/${UV_ARCHIVE_NAME}`,
      type: 'mirror',
      description: '面向中国大陆的 uv release 公益镜像',
    },
    {
      key: 'ghproxy_fastly',
      name: 'gh-proxy (Fastly CDN)',
      url: `https://cdn.gh-proxy.com/${githubReleaseUrl}`,
      type: 'mirror',
      description: 'Fastly CDN 镜像',
    },
    {
      key: 'ghproxy_cloudflare',
      name: 'gh-proxy (Cloudflare)',
      url: `https://gh-proxy.com/${githubReleaseUrl}`,
      type: 'mirror',
      description: 'Cloudflare CDN 镜像',
    },
    {
      key: 'ghproxy_edgeone',
      name: 'gh-proxy (EdgeOne)',
      url: `https://edgeone.gh-proxy.com/${githubReleaseUrl}`,
      type: 'mirror',
      description: 'EdgeOne CDN 镜像',
    },
    {
      key: 'ghfast',
      name: 'ghfast 镜像',
      url: `https://ghfast.top/${githubReleaseUrl}`,
      type: 'mirror',
      description: '第三方 GitHub Release 镜像，低优先级尝试',
    },
    {
      key: 'github',
      name: 'GitHub 官方',
      url: githubReleaseUrl,
      type: 'official',
      description: 'Astral 官方 GitHub Release，作为最终兜底',
    },
  ]
}

export function mergeUvMirrors(
  version: string,
  configuredMirrors: MirrorSource[] = []
): MirrorSource[] {
  const defaults = createUvMirrors(version)
  const defaultsByKey = new Map(defaults.map(mirror => [mirror.key, mirror]))
  const legacyKeys: Record<string, string> = {
    ghproxy: 'ghproxy_cloudflare',
    official: 'github',
  }
  const merged: MirrorSource[] = []
  const usedKeys = new Set<string>()

  for (const configured of configuredMirrors) {
    const key = legacyKeys[configured.key] || configured.key
    if (usedKeys.has(key)) {
      continue
    }

    const currentDefault = defaultsByKey.get(key)
    if (currentDefault) {
      merged.push({ ...currentDefault, ...configured, key, url: currentDefault.url })
      usedKeys.add(key)
      continue
    }

    if (configured.url.includes('/latest/') || configured.url.toLowerCase().endsWith('/uv.exe')) {
      continue
    }

    merged.push(configured)
    usedKeys.add(key)
  }

  for (const defaultMirror of defaults) {
    if (!usedKeys.has(defaultMirror.key)) {
      merged.push(defaultMirror)
    }
  }

  return merged
}

export function createUvChecksumUrls(version: string): string[] {
  const githubChecksumUrl = `${getGithubReleaseUrl(version)}.sha256`

  return [
    githubChecksumUrl,
    `https://releases.astral.sh/github/uv/releases/download/${version}/${UV_ARCHIVE_NAME}.sha256`,
  ]
}

/**
 * 在目标目录内以事务方式替换 uv 可执行文件。
 *
 * 所有候选文件先复制到目标卷，再备份旧文件并统一激活。安装后验证失败时，
 * 恢复全部旧文件，避免初始化留下半套 uv 工具。
 */
export async function deployUvBinaries(
  stageDir: string,
  scriptsDir: string,
  binaryNames: string[],
  validate: () => Promise<void>,
  fileSystem: UvDeploymentFileSystem = fs
): Promise<void> {
  const token = `${process.pid}-${Date.now()}`
  const entries: UvDeploymentEntry[] = binaryNames.map(binaryName => ({
    targetPath: path.join(scriptsDir, binaryName),
    candidatePath: path.join(scriptsDir, `.${binaryName}.${token}.new`),
    backupPath: path.join(scriptsDir, `.${binaryName}.${token}.bak`),
    backupCreated: false,
    activated: false,
  }))
  let committed = false

  try {
    for (let index = 0; index < entries.length; index++) {
      fileSystem.copyFileSync(
        path.join(stageDir, binaryNames[index]),
        entries[index].candidatePath,
        fileSystem.constants.COPYFILE_EXCL
      )
    }

    for (const entry of entries) {
      if (fileSystem.existsSync(entry.targetPath)) {
        fileSystem.renameSync(entry.targetPath, entry.backupPath)
        entry.backupCreated = true
      }
      fileSystem.renameSync(entry.candidatePath, entry.targetPath)
      entry.activated = true
    }

    await validate()
    committed = true
  } catch (error) {
    const rollbackErrors: string[] = []

    for (const entry of [...entries].reverse()) {
      try {
        if (entry.activated && fileSystem.existsSync(entry.targetPath)) {
          fileSystem.unlinkSync(entry.targetPath)
        }
        if (entry.backupCreated && fileSystem.existsSync(entry.backupPath)) {
          fileSystem.renameSync(entry.backupPath, entry.targetPath)
        }
      } catch (rollbackError) {
        rollbackErrors.push(
          `${path.basename(entry.targetPath)}: ${
            rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
          }`
        )
      }
    }

    const message = error instanceof Error ? error.message : String(error)
    throw new Error(
      rollbackErrors.length > 0
        ? `${message}；uv 部署回滚不完整：${rollbackErrors.join('；')}`
        : message
    )
  } finally {
    for (const entry of entries) {
      try {
        if (fileSystem.existsSync(entry.candidatePath)) {
          fileSystem.rmSync(entry.candidatePath, { force: true })
        }
      } catch {
        // 清理失败不能覆盖部署或回滚结果。
      }
      try {
        if (committed && fileSystem.existsSync(entry.backupPath)) {
          fileSystem.rmSync(entry.backupPath, { force: true })
        }
      } catch {
        // 唯一命名的备份可由后续维护流程清理。
      }
    }
  }
}
