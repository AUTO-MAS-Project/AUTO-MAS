import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const git = (...args) =>
  execFileSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
const args = process.argv.slice(2)
const check = args[0] === '--check'
if ((check && args.length !== 2) || (!check && (args.length > 1 || args[0]?.startsWith('--')))) {
  console.error('Usage: audit-baseline.mjs [ref] | --check <base-ref>')
  process.exit(2)
}
const ref = check ? undefined : args[0]
const treeFiles = ref => git('ls-tree', '-r', '-z', '--name-only', ref).split('\0').filter(Boolean)
const files = ref
  ? treeFiles(ref)
  : git('ls-files', '-z', '--cached', '--others', '--exclude-standard').split('\0').filter(Boolean)
const lineCount = source =>
  source ? source.split(/\r\n|\r|\n/).length - Number(/[\r\n]$/.test(source)) : 0
const readSources = (ref, files) => {
  const sources = new Map()
  const selected = files.filter(
    file => file.startsWith('frontend/') && /\.(ts|vue|css)$/.test(file)
  )
  if (!selected.length) return sources
  const batch = execFileSync('git', ['cat-file', '--batch', '-z'], {
    cwd: root,
    input: selected.map(file => `${ref}:${file}\0`).join(''),
    maxBuffer: 64 * 1024 * 1024,
  })
  let offset = 0
  for (const file of selected) {
    const end = batch.indexOf(10, offset)
    const size = Number(batch.subarray(offset, end).toString().split(' ')[2])
    sources.set(file, batch.subarray(end + 1, end + 1 + size).toString('utf8'))
    offset = end + 1 + size + 1
  }
  return sources
}

if (check) {
  let base
  try {
    base = git('rev-parse', '--verify', '--end-of-options', `${args[1]}^{commit}`).trim()
  } catch {
    console.error(`无法读取基线提交：${args[1]}`)
    process.exit(1)
  }
  const isVue = file => file.startsWith('frontend/src/') && file.endsWith('.vue')
  const baseSources = readSources(base, treeFiles(base).filter(isVue))
  const renames = new Map()
  const changes = git('diff', '--name-status', '-z', '--find-renames', base, '--', 'frontend/src')
    .split('\0')
    .filter(Boolean)
  for (let index = 0; index < changes.length;) {
    const status = changes[index++]
    const previous = changes[index++]
    if (status.startsWith('R')) renames.set(changes[index++], previous)
  }
  let checked = 0
  let violations = 0
  for (const file of new Set(files.filter(isVue))) {
    if (!existsSync(path.join(root, file))) continue
    const baseline = lineCount(baseSources.get(renames.get(file) ?? file))
    const limit = Math.max(500, baseline)
    const lines = lineCount(readFileSync(path.join(root, file), 'utf8'))
    checked++
    if (lines > limit) {
      violations++
      console.error(`${file}: ${lines} 行超过上限 ${limit} 行（基线 ${baseline} 行）`)
    }
  }
  console.log(`组件尺寸检查：${checked} 个文件，${violations} 处超限；基线 ${base}`)
  process.exit(violations ? 1 : 0)
}

const groups = {}
const vueFiles = []
const sources = ref ? readSources(ref, files) : new Map()
for (const file of new Set(files)) {
  if (!ref && !existsSync(path.join(root, file))) continue
  if (
    !file.startsWith('frontend/') ||
    !/\.(ts|vue|css)$/.test(file) ||
    /\.(test|spec)\./.test(file)
  )
    continue
  const group = file.startsWith('frontend/src/api/')
    ? 'generatedApi'
    : file.startsWith('frontend/src/i18n/')
      ? 'i18n'
      : file.startsWith('frontend/electron/')
        ? 'electron'
        : file.startsWith('frontend/src/')
          ? 'renderer'
          : undefined
  if (!group) continue
  const source = ref ? sources.get(file) : readFileSync(path.join(root, file), 'utf8')
  const lines = lineCount(source)
  const total = (groups[group] ??= { files: 0, lines: 0 })
  total.files++
  total.lines += lines
  if (file.endsWith('.vue') && group === 'renderer') vueFiles.push({ file, lines })
}
console.log(
  JSON.stringify(
    {
      ref: ref ? git('rev-parse', ref).trim() : 'working-tree',
      head: git('rev-parse', 'HEAD').trim(),
      node: process.version,
      groups,
      vue: {
        files: vueFiles.length,
        over500: vueFiles.filter(f => f.lines > 500).length,
        over1000: vueFiles.filter(f => f.lines > 1000).length,
      },
      largestVue: vueFiles.sort((a, b) => b.lines - a.lines).slice(0, 10),
    },
    null,
    2
  )
)
