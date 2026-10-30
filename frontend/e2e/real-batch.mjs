#!/usr/bin/env node
// 批量跑本机已启用用户的真实专项：每个目标一次独立运行（独立隔离数据根、独立真实运行锁），
// 一个目标失败不影响其余；结果写到 test-results/real-batch/<序号-专项-账号>/。
// 用法：yarn e2e:real:all [--list] [--only MaaConfig,SrcConfig] [其余参数透传给 playwright]
// ponytail: 每个目标重启整套服务，固定开销约 20-30s；等单批目标多到不能接受时再复用后端。
import { spawn } from 'node:child_process'
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { listRealCandidates, readRealScripts } from './run.mjs'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = path.resolve(frontendRoot, '..')

export const selectBatchTargets = (candidates, only = []) => {
  if (only.length === 0) return candidates
  const known = new Set(candidates.map(candidate => candidate.scriptType))
  const unknown = only.filter(type => !known.has(type))
  if (unknown.length > 0) {
    throw new Error('本机 config 里没有这些专项的已启用用户: ' + unknown.join(', '))
  }
  return candidates.filter(candidate => only.includes(candidate.scriptType))
}

const slug = value => String(value).replace(/[^\w.-]+/g, '_')

const readSummary = async outputDir => {
  try {
    const entries = await readdir(outputDir, { recursive: true, withFileTypes: true })
    const hit = entries.find(entry => entry.isFile() && entry.name === 'real-e2e-summary.json')
    if (!hit) return undefined
    const file = path.join(hit.parentPath ?? hit.path, hit.name)
    return JSON.parse(await readFile(file, 'utf8'))
  } catch {
    return undefined
  }
}

const runTarget = (target, forwarded, outputDir) =>
  new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      AUTO_MAS_E2E_REAL: '1',
      AUTO_MAS_E2E_SCRIPT_ID: target.scriptId,
      AUTO_MAS_E2E_USER_ID: target.userId,
      AUTO_MAS_E2E_ACCOUNT_NAME: target.accountName,
    }
    // 模拟器由每个目标自己的脚本绑定决定，避免上一个目标的显式覆盖串到下一个
    delete env.AUTO_MAS_E2E_EMULATOR_ID
    delete env.AUTO_MAS_E2E_EMULATOR_INDEX
    const child = spawn(
      process.execPath,
      [path.join(frontendRoot, 'e2e', 'run.mjs'), ...forwarded, '--output', outputDir],
      { cwd: frontendRoot, stdio: 'inherit', windowsHide: true, env }
    )
    child.once('error', reject)
    child.once('exit', code => resolve(code ?? 1))
  })

async function main() {
  const argv = process.argv.slice(2)
  if (argv.includes('--in-place') || process.env.AUTO_MAS_E2E_IN_PLACE === '1') {
    throw new Error(
      '批量模式要求每个目标独立数据根，不支持 --in-place；调试单个目标请用 yarn e2e:real'
    )
  }
  const only = []
  const forwarded = []
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--only') {
      only.push(
        ...String(argv[index + 1] ?? '')
          .split(',')
          .map(type => type.trim())
          .filter(Boolean)
      )
      index += 1
    } else {
      forwarded.push(argv[index])
    }
  }
  if (!forwarded.includes('--grep')) forwarded.push('--grep', '@real')

  const sourceRoot = path.resolve(process.env.AUTO_MAS_E2E_TEMPLATE_ROOT?.trim() || repositoryRoot)
  const scriptConfig = await readRealScripts(sourceRoot)
  const candidates = listRealCandidates(scriptConfig)
  if (candidates.length === 0) {
    throw new Error(
      '本机 config 里没有已启用的脚本用户：' +
        sourceRoot +
        '。先在应用里配一个用户；在 worktree 里跑时用 AUTO_MAS_E2E_TEMPLATE_ROOT 指向主检出'
    )
  }
  const targets = selectBatchTargets(candidates, only)
  if (targets.length === 0) throw new Error('没有匹配的批量目标: ' + only.join(', '))
  if (argv.includes('--list')) {
    for (const [index, target] of targets.entries()) {
      console.log(
        index +
          1 +
          '. ' +
          target.scriptType +
          ' / ' +
          target.accountName +
          '  ' +
          target.scriptId +
          '  ' +
          target.userId
      )
    }
    console.log('共 ' + targets.length + ' 个目标')
    return
  }

  const results = []
  for (const [index, target] of targets.entries()) {
    const outputDir = path.join(
      'test-results',
      'real-batch',
      index + 1 + '-' + slug(target.scriptType) + '-' + slug(target.accountName)
    )
    console.log('')
    console.log(
      '[e2e:batch] ' +
        (index + 1) +
        '/' +
        targets.length +
        ' ' +
        target.scriptType +
        ' / ' +
        target.accountName
    )
    const code = await runTarget(target, forwarded, outputDir)
    results.push({
      target,
      code,
      outputDir,
      summary: await readSummary(path.join(frontendRoot, outputDir)),
    })
  }

  console.log('')
  console.log('[e2e:batch] 汇总')
  for (const result of results) {
    const status = result.code === 0 ? 'PASS' : 'FAIL(' + result.code + ')'
    const summary = result.summary
    const detail = summary
      ? ' scheduler=' + summary.scheduler + ' accepted=' + summary.accountResultAccepted
      : ''
    console.log(
      '  ' +
        status +
        '  ' +
        result.target.scriptType +
        ' / ' +
        result.target.accountName +
        detail +
        '  ' +
        result.outputDir
    )
  }
  const failed = results.filter(result => result.code !== 0)
  console.log('  通过 ' + (results.length - failed.length) + ' / ' + results.length)
  if (failed.length > 0) process.exitCode = 1
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
