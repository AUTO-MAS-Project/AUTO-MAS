import * as fs from 'fs'
import AdmZip = require('adm-zip')
import type {
  InstalledMascot,
  MascotImportResult,
  MascotManifest,
  MascotSummary,
} from '../../src/types/mascotPack'
import {
  ASSET_PACKAGE_LIMITS,
  AssetPackageError,
  AssetPackageStore,
  assertPlainObject,
  fail,
  normalizePackageInfo,
  type LoadedAssetPackage,
} from './assetPackageService'
import { readAppearancePackage } from './appearanceService'
import { mascotAssetPaths, normalizeMascot, validateMascotAssets } from './mascotManifest'

const store = new AssetPackageStore<MascotManifest>({
  directoryName: 'mascots',
  manifestName: 'mascot.json',
  normalize(value) {
    const info = normalizePackageInfo(value, 'mascot.json')
    const raw = assertPlainObject(value, 'mascot.json')
    const mascot = normalizeMascot(raw.mascot)
    if (!mascot) fail('桌宠包缺少 mascot')
    return { ...info, mascot }
  },
  referencedPaths: manifest => [
    ...mascotAssetPaths(manifest.mascot),
    ...(manifest.preview ? [manifest.preview] : []),
  ],
  validateAssets: (manifest, read) => validateMascotAssets(manifest.mascot, read),
})

export const getMascotRoot = (userDataPath: string): string => store.root(userDataPath)

/** 商店只接收纯桌宠包；本地导入仍可从旧主题包提取桌宠。 */
export function inspectMascotPackage(zipPath: string): {
  manifest: MascotManifest
  previewUrl?: string
} {
  const { manifest, files } = store.readArchive(zipPath)
  const preview = files.find(
    file => file.path.toLowerCase() === (manifest.preview ?? manifest.mascot.path).toLowerCase()
  )
  return {
    manifest,
    ...(preview
      ? { previewUrl: `data:${preview.mime};base64,${preview.data.toString('base64')}` }
      : {}),
  }
}

function serializeMascot({
  manifest,
  assets,
}: LoadedAssetPackage<MascotManifest>): InstalledMascot {
  return {
    ...manifest,
    mascotUrl: assets[manifest.mascot.path],
    ...(manifest.preview ? { previewUrl: assets[manifest.preview] } : {}),
    ...(manifest.mascot.animation
      ? {
          mascotAnimationUrl: assets[manifest.mascot.animation.path],
          mascotLookUrl: assets[manifest.mascot.animation.lookPath ?? ''],
          mascotResultUrl: assets[manifest.mascot.animation.resultPath ?? ''],
        }
      : {}),
  }
}

function summarizeMascot({ manifest, assets }: LoadedAssetPackage<MascotManifest>): MascotSummary {
  return {
    id: manifest.id,
    name: manifest.name,
    ...(manifest.description ? { description: manifest.description } : {}),
    ...(manifest.preview ? { previewUrl: assets[manifest.preview] } : {}),
  }
}

/** 旧主题包可直接作为桌宠来源；只安装桌宠图片，不安装主题。 */
export function importMascotPackage(
  userDataPath: string,
  zipPath: string,
  replace = false
): MascotImportResult {
  try {
    const stat = fs.statSync(zipPath)
    if (!stat.isFile() || stat.size > ASSET_PACKAGE_LIMITS.archiveBytes) fail('桌宠 ZIP 无效或过大')
    const hasMascotManifest = Boolean(new AdmZip(zipPath).getEntry('mascot.json'))
    let pack: ReturnType<typeof store.readArchive>
    if (hasMascotManifest) {
      pack = store.readArchive(zipPath)
    } else {
      const { manifest: theme, files } = readAppearancePackage(zipPath)
      if (!theme.mascot) fail('主题包没有附带桌宠')
      const manifest: MascotManifest = {
        formatVersion: 1,
        id: theme.id,
        name: theme.name,
        ...(theme.description ? { description: theme.description } : {}),
        mascot: theme.mascot,
      }
      const expectedPaths = new Set(
        mascotAssetPaths(manifest.mascot).map(item => item.toLowerCase())
      )
      pack = { manifest, files: files.filter(file => expectedPaths.has(file.path.toLowerCase())) }
    }
    const { item, existing, ...result } = store.install(userDataPath, pack, replace)
    return {
      ...result,
      code: result.code === 'UNSUPPORTED' ? 'IMPORT_FAILED' : result.code,
      ...(item ? { mascot: summarizeMascot(item) } : {}),
      ...(existing ? { existing: summarizeMascot(existing) } : {}),
    }
  } catch (error) {
    return {
      success: false,
      code:
        error instanceof AssetPackageError && error.code === 'INVALID_ANIMATION'
          ? 'INVALID_ANIMATION'
          : 'INVALID_PACKAGE',
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

export function listMascots(userDataPath: string): MascotSummary[] {
  return store.list(userDataPath, 'preview').map(summarizeMascot)
}

export function getMascot(userDataPath: string, id: string): InstalledMascot | null {
  const item = store.get(userDataPath, id)
  return item ? serializeMascot(item) : null
}

export const removeMascot = (userDataPath: string, id: string) => store.remove(userDataPath, id)
