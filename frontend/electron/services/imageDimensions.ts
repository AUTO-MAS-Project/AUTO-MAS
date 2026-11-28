export interface ImageDimensions {
  width: number
  height: number
}

/**
 * 从 PNG / JPEG / WebP 原始字节读取像素尺寸，用于上传封面裁切比例预检。
 * 不解码整图，格式异常时安全返回 null。
 */
export function getImageDimensions(data: Buffer): ImageDimensions | null {
  if (data.length >= 24 && data.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'))) {
    const width = data.readUInt32BE(16)
    const height = data.readUInt32BE(20)
    return width > 0 && height > 0 ? { width, height } : null
  }

  if (
    data.length >= 30 &&
    data.subarray(0, 4).toString('latin1') === 'RIFF' &&
    data.subarray(8, 12).toString('latin1') === 'WEBP'
  ) {
    const chunk = data.subarray(12, 16).toString('latin1')
    if (chunk === 'VP8X' && data.length >= 30) {
      const width = 1 + (data[24] | (data[25] << 8) | (data[26] << 16))
      const height = 1 + (data[27] | (data[28] << 8) | (data[29] << 16))
      return width > 0 && height > 0 ? { width, height } : null
    }
    if (
      chunk === 'VP8 ' &&
      data.length >= 30 &&
      data[23] === 0x9d &&
      data[24] === 0x01 &&
      data[25] === 0x2a
    ) {
      const width = data.readUInt16LE(26) & 0x3fff
      const height = data.readUInt16LE(28) & 0x3fff
      return width > 0 && height > 0 ? { width, height } : null
    }
    if (chunk === 'VP8L' && data.length >= 25 && data[20] === 0x2f) {
      const bits = data.readUInt32LE(21)
      const width = (bits & 0x3fff) + 1
      const height = ((bits >> 14) & 0x3fff) + 1
      return width > 0 && height > 0 ? { width, height } : null
    }
  }

  if (data.length >= 4 && data[0] === 0xff && data[1] === 0xd8) {
    let offset = 2
    while (offset + 4 <= data.length) {
      if (data[offset] !== 0xff) break
      while (offset < data.length && data[offset] === 0xff) offset += 1
      if (offset >= data.length) break
      const marker = data[offset]
      offset += 1
      if (marker === 0xd9 || marker === 0xda) break
      if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue
      if (offset + 2 > data.length) break
      const length = data.readUInt16BE(offset)
      if (length < 2 || offset + length > data.length) break
      const isSof =
        (marker >= 0xc0 && marker <= 0xc3) ||
        (marker >= 0xc5 && marker <= 0xc7) ||
        (marker >= 0xc9 && marker <= 0xcb) ||
        (marker >= 0xcd && marker <= 0xcf)
      if (isSof && length >= 7) {
        const height = data.readUInt16BE(offset + 3)
        const width = data.readUInt16BE(offset + 5)
        return width > 0 && height > 0 ? { width, height } : null
      }
      offset += length
    }
  }

  return null
}
