import { spawn } from 'node:child_process'
import { readdir, stat } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(import.meta.url)
const reportBase = path.join(frontendRoot, 'playwright-report')

/** 每次运行的报告都在自己的目录里，按运行时间排序后取最新的一份。 */
const listReports = async () => {
  const found = []
  for (const mode of ['browser', 'real']) {
    const modeDir = path.join(reportBase, mode)
    let entries = []
    try {
      entries = await readdir(modeDir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const index = path.join(modeDir, entry.name, 'index.html')
      try {
        found.push({
          mode,
          tag: entry.name,
          dir: path.join(modeDir, entry.name),
          at: (await stat(index)).mtimeMs,
        })
      } catch {
        // 没有 index.html 的目录不是可看的报告
      }
    }
  }
  return found.sort((left, right) => right.at - left.at)
}

const reports = await listReports()
if (reports.length === 0) {
  console.error('还没有任何 E2E 报告。先跑 yarn e2e（或 yarn e2e --grep <tag>）。')
  process.exit(1)
}

const explicit = process.argv[2]?.trim()
const target = explicit
  ? reports.find(report => report.tag === explicit || report.mode === explicit)
  : reports[0]
if (!target) {
  console.error(
    `找不到报告 "${explicit}"。现有报告：\n${reports.map(report => `  ${report.mode}/${report.tag}`).join('\n')}`
  )
  process.exit(1)
}

console.log(`打开报告 ${target.mode}/${target.tag}（共 ${reports.length} 份，最新在前）`)
for (const report of reports.slice(0, 10)) {
  console.log(
    `  ${report.mode === target.mode && report.tag === target.tag ? '→' : ' '} ${report.mode}/${report.tag}`
  )
}
const cli = path.join(path.dirname(require.resolve('@playwright/test/package.json')), 'cli.js')
const child = spawn(process.execPath, [cli, 'show-report', target.dir], {
  cwd: frontendRoot,
  stdio: 'inherit',
  windowsHide: true,
})
child.on('exit', code => process.exit(code ?? 0))
