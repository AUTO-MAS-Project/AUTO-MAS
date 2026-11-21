// Windows 桌面构建使用系统自带的 .NET Framework 编译器。
const { execFileSync } = require('node:child_process')
const { mkdirSync, existsSync } = require('node:fs')
const path = require('node:path')
if (process.platform === 'win32') {
  const root = path.resolve(__dirname, '..')
  const out = path.join(root, 'dist-electron', 'startup-probe.exe')
  mkdirSync(path.dirname(out), { recursive: true })
  const framework = path.join(process.env.SystemRoot, 'Microsoft.NET')
  const compiler = path.join(
    framework,
    existsSync(path.join(framework, 'Framework64', 'v4.0.30319', 'csc.exe'))
      ? 'Framework64'
      : 'Framework',
    'v4.0.30319',
    'csc.exe'
  )
  execFileSync(
    compiler,
    [
      '/nologo',
      '/optimize+',
      '/platform:anycpu',
      '/target:exe',
      '/reference:System.Management.dll',
      '/reference:System.Web.Extensions.dll',
      '/out:' + out,
      ...['Probe', 'Counters', 'Storage', 'Adapters', 'OwnedProcesses'].map(name =>
        path.join(root, 'native', 'startup', name + '.cs')
      ),
    ],
    { stdio: 'inherit', windowsHide: true }
  )
}
