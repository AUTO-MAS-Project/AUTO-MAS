import * as fs from 'fs'
import * as path from 'path'

interface IntegrationSnapshotReleasePolicy {
  channel: 'experimental-alpha'
  embeddedUpdater: 'manual-only'
}

interface PackagedRuntimeIdentity {
  isPackaged: boolean
  version?: string
  metadata?: unknown
}

type JsonRecord = Record<string, unknown>

const experimentalAlphaRuntimeEnvironment = Object.freeze({
  AUTO_MAS_RELEASE_CHANNEL: 'experimental-alpha',
  AUTO_MAS_EMBEDDED_UPDATE_POLICY: 'manual-only',
})

function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getSnapshotCandidates(appRoot: string): string[] {
  const candidates = [path.join(appRoot, 'res', 'integration-snapshot.json')]
  const resourcesPath = (process as NodeJS.Process & { resourcesPath?: string }).resourcesPath
  if (typeof resourcesPath === 'string' && resourcesPath.trim()) {
    candidates.push(path.join(resourcesPath, 'integration-snapshot', 'manifest.json'))
  }
  return candidates
}

function readReleasePolicy(appRoot: string): IntegrationSnapshotReleasePolicy | null {
  const snapshotPath = getSnapshotCandidates(appRoot).find(candidate => fs.existsSync(candidate))
  if (!snapshotPath) return null

  try {
    const document = JSON.parse(
      fs.readFileSync(snapshotPath, 'utf8').replace(/^\uFEFF/, '')
    ) as unknown
    if (!isJsonRecord(document)) return null
    if (document.schema_version !== 1 || document.deployment_mode !== 'bundled-snapshot') {
      return null
    }

    const policy = document.release_policy
    if (!isJsonRecord(policy) || policy.embedded_updater !== 'manual-only') {
      return null
    }

    const hasChannel = Object.prototype.hasOwnProperty.call(policy, 'channel')
    const hasReleaseChannel = Object.prototype.hasOwnProperty.call(policy, 'release_channel')
    if (hasChannel && hasReleaseChannel && policy.channel !== policy.release_channel) {
      return null
    }
    const channel = hasChannel ? policy.channel : policy.release_channel
    if (channel !== 'experimental-alpha') return null

    return {
      channel,
      embeddedUpdater: policy.embedded_updater,
    }
  } catch {
    // Snapshot policy must fail closed: a damaged file cannot turn a stable runtime into Alpha.
    return null
  }
}

function getElectronPackagedRuntimeIdentity(): PackagedRuntimeIdentity | null {
  try {
    const electron = require('electron') as { app?: unknown }
    const app = electron.app as
      | {
          isPackaged?: unknown
          getVersion?: () => string
          getAppPath?: () => string
        }
      | undefined
    if (app?.isPackaged !== true) return null

    let version: string | undefined
    try {
      version = app.getVersion?.()
    } catch {
      // A broken version reader must not turn a packaged stable app into Alpha.
    }

    let metadata: unknown
    try {
      const appPath = app.getAppPath?.()
      if (typeof appPath === 'string' && appPath.trim()) {
        metadata = JSON.parse(
          fs.readFileSync(path.join(appPath, 'package.json'), 'utf8').replace(/^\uFEFF/, '')
        ) as unknown
      }
    } catch {
      // Version fallback below remains available for an Alpha app whose asar metadata is unreadable.
    }

    return { isPackaged: true, version, metadata }
  } catch {
    return null
  }
}

function readPackagedReleasePolicy(
  identity: PackagedRuntimeIdentity | null
): IntegrationSnapshotReleasePolicy | null {
  if (!identity?.isPackaged) return null

  if (isJsonRecord(identity.metadata)) {
    const hasChannel = Object.prototype.hasOwnProperty.call(
      identity.metadata,
      'autoMasReleaseChannel'
    )
    const hasUpdater = Object.prototype.hasOwnProperty.call(
      identity.metadata,
      'autoMasEmbeddedUpdatePolicy'
    )
    if (hasChannel || hasUpdater) {
      if (
        identity.metadata.autoMasReleaseChannel === 'experimental-alpha' &&
        identity.metadata.autoMasEmbeddedUpdatePolicy === 'manual-only'
      ) {
        return { channel: 'experimental-alpha', embeddedUpdater: 'manual-only' }
      }
      return null
    }
  }

  if (typeof identity.version === 'string' && /alpha/iu.test(identity.version)) {
    return { channel: 'experimental-alpha', embeddedUpdater: 'manual-only' }
  }
  return null
}

/** A bundled integration snapshot must never fall back to mutable online resolution. */
export function requiresBundledRuntimeLock(appRoot: string): boolean {
  return getSnapshotCandidates(appRoot).some(candidate => fs.existsSync(candidate))
}

/**
 * Packaged Alpha identity is authoritative so a damaged snapshot cannot make its updater mutable.
 * Local development still requires an explicit, complete snapshot policy.
 */
export function getBundledRuntimeReleaseEnvironment(
  appRoot: string,
  packagedIdentity: PackagedRuntimeIdentity | null = getElectronPackagedRuntimeIdentity()
): Record<string, string> {
  const packagedPolicy = readPackagedReleasePolicy(packagedIdentity)
  if (packagedPolicy) return experimentalAlphaRuntimeEnvironment
  if (packagedIdentity?.isPackaged) return {}

  const policy = readReleasePolicy(appRoot)
  if (policy?.channel !== 'experimental-alpha' || policy.embeddedUpdater !== 'manual-only') {
    return {}
  }
  return experimentalAlphaRuntimeEnvironment
}
