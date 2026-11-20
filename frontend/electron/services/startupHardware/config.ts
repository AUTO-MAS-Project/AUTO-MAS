import { captureStartupHostFailure } from '../sentry'
import { StartupHardwareLog } from './localLog'
import { app } from 'electron'
import path from 'node:path'
import { getBackendOwnership, getDeveloperBackendRepo } from '../instanceConfig'
import { getAppRoot } from '../environmentService'
import { resolveDevelopmentRuntimeRoot, resolveRuntimeLaunchMode } from '../runtime/launchConfig'
import type { ProbeConfig } from './monitor'

let log: StartupHardwareLog | undefined
export function flushStartupHardwareLog() {
  return log?.drain()
}
export function startupProbeConfig(): ProbeConfig {
  const install = path.dirname(app.getPath('exe'))
  const owned = getBackendOwnership() === 'owned'
  const managed = resolveRuntimeLaunchMode() === 'managed'
  const data = getAppRoot()
  const root = managed ? data : resolveDevelopmentRuntimeRoot(data)
  const repo = managed ? path.join(root, 'repo') : data
  const runtime = path.join(root, 'runtime')
  const directories = [
    install,
    repo,
    path.join(runtime, 'cache', 'uv'),
    path.join(runtime, 'environment', 'python'),
    managed ||
    (!!getDeveloperBackendRepo() &&
      (app.isPackaged || !!process.env.AUTO_MAS_BACKEND_RUNTIME_ROOT?.trim()))
      ? path.join(runtime, 'environment', 'venv')
      : path.join(repo, '.venv'),
    app.getPath('temp'),
    path.join(data, 'temp'),
    path.join(runtime, 'cache', 'build'),
    path.join(runtime, 'cache', 'downloads'),
  ]
  if (!owned) for (const index of [1, 2, 3, 4, 6, 7, 8]) directories[index] = ''
  return {
    log: (log ??= new StartupHardwareLog(path.join(data, 'debug'))),
    reportHostFailure: captureStartupHostFailure,
    graphics: () => app.getGPUInfo('basic'),
    executable:
      process.platform !== 'win32'
        ? undefined
        : !app.isPackaged
          ? path.join(__dirname, '..', '..', 'startup-probe.exe')
          : path.join(
              process.resourcesPath,
              'app.asar.unpacked',
              'dist-electron',
              'startup-probe.exe'
            ),
    directories,
    scope: owned ? 'managed' : 'desktop',
    acceleration: app.isHardwareAccelerationEnabled() ? 'yes' : 'no',
  }
}
