import * as path from 'path'
import type { MascotDefinition } from '../../src/types/mascotPack'
import {
  AssetPackageError,
  assertAssetPath,
  assertOptionalNumber,
  assertPlainObject,
  fail,
} from './assetPackageService'

export function normalizeMascot(value: unknown): MascotDefinition | undefined {
  if (value === undefined) return undefined
  const raw = assertPlainObject(value, 'mascot')
  const pathValue = assertAssetPath(raw.path, true)
  const width = assertOptionalNumber(raw.width, 'mascot.width', 16, 1024)
  const opacity = assertOptionalNumber(raw.opacity, 'mascot.opacity', 0, 1)
  const animation = normalizeMascotAnimation(raw.animation)
  const position = raw.position === undefined ? undefined : raw.position
  if (
    position !== undefined &&
    position !== 'top-left' &&
    position !== 'top-right' &&
    position !== 'bottom-left' &&
    position !== 'bottom-right'
  ) {
    fail('mascot.position 不受支持')
  }
  return {
    path: pathValue,
    ...(width === undefined ? {} : { width }),
    ...(opacity === undefined ? {} : { opacity }),
    ...(position === undefined ? {} : { position }),
    ...(animation === undefined ? {} : { animation }),
  }
}

function normalizeMascotAnimation(value: unknown): MascotDefinition['animation'] {
  if (value === undefined) return undefined
  try {
    const raw = assertPlainObject(value, 'mascot.animation')
    const assetPath = assertAssetPath(raw.path, true)
    const columns = assertOptionalNumber(raw.columns, 'mascot.animation.columns', 2, 16)
    const idleFps = assertOptionalNumber(raw.idleFps, 'mascot.animation.idleFps', 1, 24)
    const workingFps = assertOptionalNumber(raw.workingFps, 'mascot.animation.workingFps', 1, 24)
    const lookPath = raw.lookPath === undefined ? undefined : assertAssetPath(raw.lookPath, true)
    const resultPath =
      raw.resultPath === undefined ? undefined : assertAssetPath(raw.resultPath, true)
    const dragPath = raw.dragPath === undefined ? undefined : assertAssetPath(raw.dragPath, true)
    if (lookPath && path.posix.extname(lookPath).toLowerCase() !== '.png') {
      throw new Error('mascot.animation.lookPath requires a PNG sprite sheet')
    }
    if (resultPath && path.posix.extname(resultPath).toLowerCase() !== '.png') {
      throw new Error('mascot.animation.resultPath requires a PNG sprite sheet')
    }
    if (dragPath && path.posix.extname(dragPath).toLowerCase() !== '.png') {
      throw new Error('mascot.animation.dragPath requires a PNG sprite sheet')
    }
    if (
      path.posix.extname(assetPath).toLowerCase() !== '.png' ||
      !columns ||
      !Number.isInteger(columns)
    ) {
      throw new Error('mascot.animation requires a PNG sprite sheet and an integer column count')
    }
    return {
      path: assetPath,
      columns,
      ...(idleFps === undefined ? {} : { idleFps }),
      ...(workingFps === undefined ? {} : { workingFps }),
      ...(lookPath === undefined ? {} : { lookPath }),
      ...(resultPath === undefined ? {} : { resultPath }),
      ...(dragPath === undefined ? {} : { dragPath }),
    }
  } catch (error) {
    throw new AssetPackageError(
      'INVALID_ANIMATION',
      error instanceof Error ? error.message : String(error)
    )
  }
}

function validateMascotAnimationData(
  animation: NonNullable<MascotDefinition['animation']>,
  data: Buffer,
  rows = 2
): void {
  if (data.length < 33 || data.subarray(12, 16).toString('ascii') !== 'IHDR') {
    throw new AssetPackageError('INVALID_ANIMATION', 'mascot.animation: invalid PNG dimensions')
  }
  const width = data.readUInt32BE(16)
  const height = data.readUInt32BE(20)
  if (
    !width ||
    !height ||
    width > 8192 ||
    height > 8192 ||
    width % animation.columns !== 0 ||
    height % rows !== 0
  ) {
    throw new AssetPackageError(
      'INVALID_ANIMATION',
      `mascot.animation: expected ${rows} row(s) of equal-size frames`
    )
  }
}

export function mascotAssetPaths(mascot: MascotDefinition): string[] {
  return [
    mascot.path,
    mascot.animation?.path,
    mascot.animation?.lookPath,
    mascot.animation?.resultPath,
    mascot.animation?.dragPath,
  ].filter((value): value is string => Boolean(value))
}

export function validateMascotAssets(
  mascot: MascotDefinition | undefined,
  read: (assetPath: string) => Buffer
): void {
  if (!mascot?.animation) return
  validateMascotAnimationData(mascot.animation, read(mascot.animation.path))
  if (mascot.animation.resultPath)
    validateMascotAnimationData(mascot.animation, read(mascot.animation.resultPath))
  if (mascot.animation.dragPath)
    validateMascotAnimationData(mascot.animation, read(mascot.animation.dragPath), 1)
}
