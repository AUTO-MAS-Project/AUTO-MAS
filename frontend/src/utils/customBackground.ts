export const CUSTOM_BACKGROUND_MAX_BYTES = 8 * 1024 * 1024
export const CUSTOM_BACKGROUND_MAX_PIXELS = 16_777_216
const CUSTOM_BACKGROUND_MAX_DIMENSION = 16_384

const MIME_BY_EXTENSION: Record<string, string> = {
  bmp: 'image/bmp',
  gif: 'image/gif',
  jpeg: 'image/jpeg',
  jpg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
}

export function getCustomBackgroundExtension(path: string): string {
  const fileName = path.split(/[\\/]/).pop() ?? ''
  const dotIndex = fileName.lastIndexOf('.')
  return dotIndex < 0 ? '' : fileName.slice(dotIndex + 1).toLowerCase()
}

export function hasCustomBackgroundExtension(path: string): boolean {
  return getCustomBackgroundExtension(path) in MIME_BY_EXTENSION
}

export function getCustomBackgroundMime(path: string): string | null {
  return MIME_BY_EXTENSION[getCustomBackgroundExtension(path)] ?? null
}

function readUint32BE(bytes: Uint8Array, offset: number): number {
  return (
    bytes[offset] * 0x1000000 +
    (bytes[offset + 1] << 16) +
    (bytes[offset + 2] << 8) +
    bytes[offset + 3]
  )
}

function readInt32LE(bytes: Uint8Array, offset: number): number {
  return (
    bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16) | (bytes[offset + 3] << 24)
  )
}

function readImageDimensions(bytes: Uint8Array): { width: number; height: number } | null {
  if (
    bytes.length >= 24 &&
    bytes[0] === 0x89 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x4e &&
    bytes[3] === 0x47
  ) {
    return { width: readUint32BE(bytes, 16), height: readUint32BE(bytes, 20) }
  }

  if (
    bytes.length >= 10 &&
    bytes[0] === 0x47 &&
    bytes[1] === 0x49 &&
    bytes[2] === 0x46 &&
    bytes[3] === 0x38
  ) {
    return {
      width: bytes[6] | (bytes[7] << 8),
      height: bytes[8] | (bytes[9] << 8),
    }
  }

  if (bytes.length >= 26 && bytes[0] === 0x42 && bytes[1] === 0x4d) {
    const headerSize = readInt32LE(bytes, 14)
    if (headerSize === 12 && bytes.length >= 26) {
      return {
        width: bytes[18] | (bytes[19] << 8),
        height: bytes[20] | (bytes[21] << 8),
      }
    }
    if (headerSize >= 40 || [16, 20, 24, 28, 32, 36].includes(headerSize)) {
      return {
        width: Math.abs(readInt32LE(bytes, 18)),
        height: Math.abs(readInt32LE(bytes, 22)),
      }
    }
  }

  if (bytes.length >= 12 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46) {
    let offset = 12
    while (offset + 8 <= bytes.length) {
      const chunkSize =
        bytes[offset + 4] +
        (bytes[offset + 5] << 8) +
        (bytes[offset + 6] << 16) +
        bytes[offset + 7] * 0x1000000
      const chunkType = String.fromCharCode(...bytes.subarray(offset, offset + 4))
      if (chunkType === 'VP8X' && offset + 30 <= bytes.length) {
        return {
          width: 1 + bytes[offset + 12] + (bytes[offset + 13] << 8) + (bytes[offset + 14] << 16),
          height: 1 + bytes[offset + 15] + (bytes[offset + 16] << 8) + (bytes[offset + 17] << 16),
        }
      }
      if (chunkType === 'VP8L' && offset + 13 <= bytes.length && bytes[offset + 8] === 0x2f) {
        const b1 = bytes[offset + 9]
        const b2 = bytes[offset + 10]
        const b3 = bytes[offset + 11]
        const b4 = bytes[offset + 12]
        return {
          width: 1 + b1 + ((b2 & 0x3f) << 8),
          height: 1 + ((b2 >> 6) | (b3 << 2) | ((b4 & 0x0f) << 10)),
        }
      }
      if (
        chunkType === 'VP8 ' &&
        offset + 30 <= bytes.length &&
        bytes[offset + 11] === 0x9d &&
        bytes[offset + 12] === 0x01 &&
        bytes[offset + 13] === 0x2a
      ) {
        return {
          width: (bytes[offset + 14] | (bytes[offset + 15] << 8)) & 0x3fff,
          height: (bytes[offset + 16] | (bytes[offset + 17] << 8)) & 0x3fff,
        }
      }
      offset += 8 + chunkSize + (chunkSize & 1)
    }
  }

  if (bytes.length >= 4 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    const startOfFrame = new Set([
      0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf,
    ])
    let offset = 2
    while (offset + 4 < bytes.length) {
      if (bytes[offset] !== 0xff) {
        offset += 1
        continue
      }
      while (bytes[offset] === 0xff) offset += 1
      const marker = bytes[offset]
      offset += 1
      if (marker === 0xd8 || marker === 0xd9 || (marker >= 0xd0 && marker <= 0xd7)) continue
      if (offset + 2 > bytes.length) break
      const segmentLength = (bytes[offset] << 8) | bytes[offset + 1]
      if (segmentLength < 2 || offset + segmentLength > bytes.length) break
      if (startOfFrame.has(marker) && segmentLength >= 7) {
        return {
          height: (bytes[offset + 3] << 8) | bytes[offset + 4],
          width: (bytes[offset + 5] << 8) | bytes[offset + 6],
        }
      }
      offset += segmentLength
    }
  }

  return null
}

export function hasSafeCustomBackgroundDimensions(base64: string): boolean {
  try {
    const binary = atob(base64)
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0))
    const dimensions = readImageDimensions(bytes)
    return Boolean(
      dimensions &&
      dimensions.width > 0 &&
      dimensions.height > 0 &&
      dimensions.width <= CUSTOM_BACKGROUND_MAX_DIMENSION &&
      dimensions.height <= CUSTOM_BACKGROUND_MAX_DIMENSION &&
      dimensions.width * dimensions.height <= CUSTOM_BACKGROUND_MAX_PIXELS
    )
  } catch {
    return false
  }
}

export function createCustomBackgroundDataUrl(base64: string, path: string): string | null {
  const mime = getCustomBackgroundMime(path)
  return base64 && mime && hasSafeCustomBackgroundDimensions(base64)
    ? `data:${mime};base64,${base64}`
    : null
}

export function clampCustomSurfaceOpacity(value: number): number {
  const opacity = Number.isFinite(value) ? value : 1
  return Math.min(1, Math.max(0.1, opacity))
}
