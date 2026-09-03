import * as fs from 'fs'
import * as zlib from 'zlib'

// ==================== CRC-32 ====================

const CRC32_TABLE = /* @__PURE__ */ (() => {
  const table = new Uint32Array(256)
  for (let i = 0; i < 256; i++) {
    let c = i
    for (let j = 0; j < 8; j++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    }
    table[i] = c
  }
  return table
})()

function crc32(data: Buffer): number {
  let crc = 0xffffffff
  for (let i = 0; i < data.length; i++) {
    crc = CRC32_TABLE[(crc ^ data[i]) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

// ==================== DOS 日期时间 ====================

function dosDateTime(date: Date): { time: number; date: number } {
  return {
    time: (date.getHours() << 11) | (date.getMinutes() << 5) | ((date.getSeconds() >> 1) & 0x1f),
    date: ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
  }
}

// ==================== 逐条写盘 ZIP ====================

interface ZipEntry {
  name: Buffer
  offset: number
  crc: number
  compressedSize: number
  uncompressedSize: number
  dosTime: number
  dosDate: number
}

/**
 * 逐条写盘的 ZIP writer，每写一个条目即落盘释放 Buffer，
 * 峰值内存仅为单条目大小，不像 AdmZip 累积全部条目。
 */
export class StreamingZipWriter {
  private fd: number
  private offset = 0
  private entries: ZipEntry[] = []

  constructor(filePath: string) {
    fs.mkdirSync(fs.realpathSync(filePath + '/..'), { recursive: true })
    this.fd = fs.openSync(filePath, 'w')
  }

  addBuffer(archivePath: string, data: Buffer): void {
    const name = Buffer.from(archivePath, 'utf-8')
    const crc = crc32(data)
    const compressed = zlib.deflateRawSync(data, { level: 6 })
    const { time, date } = dosDateTime(new Date())

    this.entries.push({
      name,
      offset: this.offset,
      crc,
      compressedSize: compressed.byteLength,
      uncompressedSize: data.byteLength,
      dosTime: time,
      dosDate: date,
    })

    const header = Buffer.alloc(30)
    header.writeUInt32LE(0x04034b50, 0)
    header.writeUInt16LE(20, 4)
    header.writeUInt16LE(0, 6)
    header.writeUInt16LE(8, 8)
    header.writeUInt16LE(time, 10)
    header.writeUInt16LE(date, 12)
    header.writeUInt32LE(crc, 14)
    header.writeUInt32LE(compressed.byteLength, 18)
    header.writeUInt32LE(data.byteLength, 22)
    header.writeUInt16LE(name.byteLength, 26)
    header.writeUInt16LE(0, 28)

    this.write(header)
    this.write(name)
    this.write(compressed)
  }

  addFile(archivePath: string, sourcePath: string): void {
    this.addBuffer(archivePath, fs.readFileSync(sourcePath))
  }

  finalize(): void {
    const centralDirOffset = this.offset

    for (const entry of this.entries) {
      const header = Buffer.alloc(46)
      header.writeUInt32LE(0x02014b50, 0)
      header.writeUInt16LE(20, 4)
      header.writeUInt16LE(20, 6)
      header.writeUInt16LE(0, 8)
      header.writeUInt16LE(8, 10)
      header.writeUInt16LE(entry.dosTime, 12)
      header.writeUInt16LE(entry.dosDate, 14)
      header.writeUInt32LE(entry.crc, 16)
      header.writeUInt32LE(entry.compressedSize, 20)
      header.writeUInt32LE(entry.uncompressedSize, 24)
      header.writeUInt16LE(entry.name.byteLength, 28)
      header.writeUInt16LE(0, 30)
      header.writeUInt16LE(0, 32)
      header.writeUInt16LE(0, 34)
      header.writeUInt16LE(0, 36)
      header.writeUInt32LE(0, 38)
      header.writeUInt32LE(entry.offset, 42)

      this.write(header)
      this.write(entry.name)
    }

    const centralDirSize = this.offset - centralDirOffset

    const eocd = Buffer.alloc(22)
    eocd.writeUInt32LE(0x06054b50, 0)
    eocd.writeUInt16LE(0, 4)
    eocd.writeUInt16LE(0, 6)
    eocd.writeUInt16LE(this.entries.length, 8)
    eocd.writeUInt16LE(this.entries.length, 10)
    eocd.writeUInt32LE(centralDirSize, 12)
    eocd.writeUInt32LE(centralDirOffset, 16)
    eocd.writeUInt16LE(0, 20)

    this.write(eocd)
    fs.closeSync(this.fd)
  }

  private write(buf: Buffer): void {
    fs.writeSync(this.fd, buf)
    this.offset += buf.byteLength
  }
}
