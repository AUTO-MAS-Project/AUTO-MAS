import { AssetPackageError } from './assetPackageService'
import { importAppearancePackage, inspectAppearancePackage } from './appearanceService'
import { importMascotPackage, inspectMascotPackage } from './mascotPackageService'
import type { PackageJob, PackageReply } from './assetPackageProcess'

const port = process.parentPort
if (!port) throw new Error('资源包处理需要父进程')
port.once('message', async ({ data }: { data: PackageJob }) => {
  let reply: PackageReply
  try {
    switch (data.operation) {
      case 'inspect-theme':
        reply = { operation: data.operation, value: await inspectAppearancePackage(data.zipPath) }
        break
      case 'inspect-mascot':
        reply = { operation: data.operation, value: await inspectMascotPackage(data.zipPath) }
        break
      case 'import-theme':
        reply = {
          operation: data.operation,
          value: await importAppearancePackage(data.userDataPath, data.zipPath, data.replace),
        }
        break
      case 'import-mascot':
        reply = {
          operation: data.operation,
          value: await importMascotPackage(data.userDataPath, data.zipPath, data.replace),
        }
        break
    }
  } catch (error) {
    reply = {
      operation: 'error',
      code: error instanceof AssetPackageError ? error.code : 'IMPORT_FAILED',
      error: error instanceof Error ? error.message : String(error),
    }
  }
  port.postMessage(reply)
})
