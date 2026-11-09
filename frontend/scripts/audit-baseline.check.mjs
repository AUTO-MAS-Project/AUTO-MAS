import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const source = fileURLToPath(new URL('./audit-baseline.mjs', import.meta.url))

function repository(t, files = {}) {
  const prefix = path.join(tmpdir(), 'mas-size-audit-')
  const root = mkdtempSync(prefix)
  t.after(() => {
    assert.ok(root.startsWith(prefix))
    rmSync(root, { recursive: true, force: true })
  })
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: 'pipe' })
  const write = (file, content) => {
    const target = path.join(root, file)
    mkdirSync(path.dirname(target), { recursive: true })
    writeFileSync(target, content)
  }
  const vue = (file, lines) =>
    write(
      `frontend/src/${file}`,
      Array.from({ length: lines }, (_, index) => `<!-- ${file} ${index} -->\n`).join('')
    )
  git('init', '--quiet')
  git('config', 'user.name', 'Size audit test')
  git('config', 'user.email', 'size-audit@example.invalid')
  git('config', 'core.autocrlf', 'false')
  write('README.md', 'Temporary repository for the component size contract.\n')
  mkdirSync(path.join(root, 'frontend/scripts'), { recursive: true })
  const script = path.join(root, 'frontend/scripts/audit-baseline.mjs')
  copyFileSync(source, script)
  for (const [file, lines] of Object.entries(files)) vue(file, lines)
  git('add', '--', '.')
  git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'baseline')
  const base = git('rev-parse', 'HEAD').trim()
  const run = (...args) =>
    spawnSync(process.execPath, [script, ...args], { cwd: root, encoding: 'utf8' })
  return { root, git, write, vue, base, run }
}

test('保留工作区和指定提交的统计报告', t => {
  const repo = repository(t, { 'Panel.vue': 500 })
  repo.vue('Panel.vue', 501)
  const current = repo.run()
  assert.equal(current.status, 0, current.stderr)
  assert.equal(JSON.parse(current.stdout).ref, 'working-tree')
  assert.equal(JSON.parse(current.stdout).vue.over500, 1)
  const baseline = repo.run(repo.base)
  assert.equal(baseline.status, 0, baseline.stderr)
  assert.equal(JSON.parse(baseline.stdout).ref, repo.base)
  assert.equal(JSON.parse(baseline.stdout).vue.over500, 0)
})

test('新增组件上限为 500 行，删除旧超限组件不能抵消增长', t => {
  const repo = repository(t, { 'Old.vue': 800 })
  rmSync(path.join(repo.root, 'frontend/src/Old.vue'))
  repo.vue('new panel.vue', 500)
  const allowed = repo.run('--check', repo.base)
  assert.equal(allowed.status, 0, allowed.stderr)
  repo.vue('new panel.vue', 501)
  const rejected = repo.run('--check', repo.base)
  assert.equal(rejected.status, 1)
  assert.match(rejected.stderr, /new panel\.vue/)
})

test('存量超限组件可以保持或缩短，但任何组件均不可越过自身上限', t => {
  const repo = repository(t, { 'Large.vue': 800, 'Small.vue': 500 })
  assert.equal(repo.run('--check', repo.base).status, 0)
  repo.vue('Large.vue', 801)
  const growth = repo.run('--check', repo.base)
  assert.equal(growth.status, 1)
  assert.match(growth.stderr, /Large\.vue/)
  repo.vue('Large.vue', 799)
  assert.equal(repo.run('--check', repo.base).status, 0)
  repo.vue('Small.vue', 501)
  const newlyOversized = repo.run('--check', repo.base)
  assert.equal(newlyOversized.status, 1)
  assert.match(newlyOversized.stderr, /Small\.vue/)
})

test('Git 识别的重命名继承旧组件基线，删除组件无需配额', t => {
  const repo = repository(t, { 'Large.vue': 800 })
  repo.git('mv', 'frontend/src/Large.vue', 'frontend/src/renamed panel.vue')
  const renamed = repo.run('--check', repo.base)
  assert.equal(renamed.status, 0, renamed.stderr)
  repo.write(
    'frontend/src/renamed panel.vue',
    Array.from({ length: 801 }, (_, index) => `<!-- Large.vue ${index} -->\n`).join('')
  )
  const growth = repo.run('--check', repo.base)
  assert.equal(growth.status, 1)
  assert.match(growth.stderr, /renamed panel\.vue/)
  repo.git('rm', '-f', 'frontend/src/renamed panel.vue')
  assert.equal(repo.run('--check', repo.base).status, 0)
})

test('未跟踪文件按真实物理行计数，忽略文件不进入门禁', t => {
  const repo = repository(t)
  repo.write('.gitignore', 'frontend/src/Ignored.vue\n')
  repo.vue('Ignored.vue', 1000)
  repo.write('frontend/src/Empty.vue', '')
  repo.write('frontend/src/NoFinalNewline.vue', Array(500).fill('line').join('\r\n'))
  const allowed = repo.run('--check', repo.base)
  assert.equal(allowed.status, 0, allowed.stderr)
  repo.write('frontend/src/NoFinalNewline.vue', Array(501).fill('line').join('\r\n'))
  const rejected = repo.run('--check', repo.base)
  assert.equal(rejected.status, 1)
  assert.match(rejected.stderr, /NoFinalNewline\.vue/)
})

test('缺少或无效基线明确失败，不猜测其他提交', t => {
  const repo = repository(t)
  assert.notEqual(repo.run('--check').status, 0)
  const invalid = repo.run('--check', 'missing-base')
  assert.notEqual(invalid.status, 0)
  assert.match(invalid.stderr, /missing-base/)
})
