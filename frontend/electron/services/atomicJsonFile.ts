import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'

/** Persist JSON without ever exposing a truncated destination file. */
export function writeJsonFileAtomically(targetPath: string, value: unknown): void {
  const directory = path.dirname(targetPath)
  fs.mkdirSync(directory, { recursive: true })
  const temporaryPath = path.join(
    directory,
    `.${path.basename(targetPath)}.${process.pid}.${Date.now()}.${crypto.randomUUID()}.tmp`
  )
  let descriptor: number | null = null

  try {
    descriptor = fs.openSync(temporaryPath, 'wx', 0o600)
    fs.writeFileSync(descriptor, `${JSON.stringify(value, null, 2)}\n`, 'utf-8')
    fs.fsyncSync(descriptor)
    fs.closeSync(descriptor)
    descriptor = null
    fs.renameSync(temporaryPath, targetPath)
  } catch (error) {
    if (descriptor !== null) {
      try {
        fs.closeSync(descriptor)
      } catch {
        // Preserve the original write/rename error.
      }
    }
    try {
      fs.rmSync(temporaryPath, { force: true })
    } catch {
      // Preserve the original write/rename error.
    }
    throw error
  }
}
