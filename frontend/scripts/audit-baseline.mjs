import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const git = (...args) =>
  execFileSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
const ref = process.argv[2]
const files = (
  ref
    ? git('ls-tree', '-r', '--name-only', ref)
    : git('ls-files', '--cached', '--others', '--exclude-standard')
)
  .trim()
  .split('\n')
const groups = {}
const vueFiles = []
const sources = new Map()
if (ref) {
  const selected = files.filter(
    file => file.startsWith('frontend/') && /\.(ts|vue|css)$/.test(file)
  )
  const batch = execFileSync('git', ['cat-file', '--batch'], {
    cwd: root,
    input: selected.map(file => `${ref}:${file}\n`).join(''),
    maxBuffer: 64 * 1024 * 1024,
  })
  let offset = 0
  for (const file of selected) {
    const end = batch.indexOf(10, offset)
    const size = Number(batch.subarray(offset, end).toString().split(' ')[2])
    sources.set(file, batch.subarray(end + 1, end + 1 + size).toString('utf8'))
    offset = end + 1 + size + 1
  }
}
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
  const lines = source ? source.split(/\r?\n/).length - Number(source.endsWith('\n')) : 0
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
