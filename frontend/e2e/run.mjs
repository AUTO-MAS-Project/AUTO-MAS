import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'
import { cp, lstat, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(import.meta.url)
const supportedScriptTypes = new Set([
  'MaaConfig',
  'GeneralConfig',
  'OkwwConfig',
  'OkNteConfig',
  'SrcConfig',
  'MaaEndConfig',
  'MaaFWConfig',
  'HSRConfig',
  'BetterGIConfig',
  'ZzzOdConfig',
  'BAAHConfig',
  'WhimboxConfig',
])

export async function acquireRealRunLock(lockPath = path.join(tmpdir(), 'auto-mas-e2e-real.lock')) {
  try {
    await writeFile(lockPath, `${process.pid}\n`, { flag: 'wx' })
  } catch (error) {
    if (error.code !== 'EEXIST') throw error
    let ownerPid = 0
    try {
      ownerPid = Number.parseInt((await readFile(lockPath, 'utf8')).trim(), 10)
    } catch {
      // Lock creation may still be in progress; keep the lock rather than racing it.
    }
    if (ownerPid > 0 && ownerPid !== process.pid) {
      try {
        process.kill(ownerPid, 0)
      } catch (probeError) {
        if (probeError.code === 'ESRCH') {
          // ponytail: 强制终止后的锁需人工确认；无人值守运行时再升级为租约锁。
          throw new Error('发现上次中断留下的真实 E2E 锁；确认没有真实测试运行后手动删除锁文件')
        }
      }
    }
    throw new Error('已有本机真实 E2E 正在运行，请等待其完成或清理残留锁文件')
  }
  return async () => {
    try {
      if (Number.parseInt((await readFile(lockPath, 'utf8')).trim(), 10) === process.pid) {
        await rm(lockPath, { force: true })
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error
    }
  }
}

const readConfig = async file => {
  try {
    const details = await lstat(file)
    if (details.isSymbolicLink() || !details.isFile()) throw new Error('invalid file')
    return JSON.parse((await readFile(file, 'utf8')).replace(/^\uFEFF/, ''))
  } catch {
    throw new Error(`无法读取 E2E 配置 ${path.basename(file)}`)
  }
}

const selectEntry = (collection, id) => {
  const entry = collection.instances?.find(item => item.uid === id)
  if (!entry || !collection[id]) throw new Error('所选 E2E 配置项不存在')
  return { instances: [entry], [id]: collection[id] }
}

export async function seedRealProfile(sourceRoot, dataRoot, env) {
  const required = ['SCRIPT_ID', 'USER_ID', 'ACCOUNT_NAME']
  for (const key of required) {
    if (!env[`AUTO_MAS_E2E_${key}`]?.trim()) throw new Error(`缺少 AUTO_MAS_E2E_${key}`)
  }
  for (const key of ['SCRIPT_ID', 'USER_ID']) {
    if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(env[`AUTO_MAS_E2E_${key}`])) {
      throw new Error(`AUTO_MAS_E2E_${key} 必须是配置 UUID`)
    }
  }

  const scriptId = env.AUTO_MAS_E2E_SCRIPT_ID
  const userId = env.AUTO_MAS_E2E_USER_ID
  sourceRoot = path.resolve(sourceRoot)
  const sourceConfig = path.join(sourceRoot, 'config')
  const scripts = selectEntry(
    await readConfig(path.join(sourceConfig, 'ScriptConfig.json')),
    scriptId
  )
  const script = scripts[scriptId]
  const scriptType = scripts.instances[0].type
  if (!supportedScriptTypes.has(scriptType)) {
    throw new Error(`真实 E2E 尚未登记专项类型 ${scriptType}，请由专项作者补充适配`)
  }
  const emulatorId = typeof script.Emulator?.Id === 'string' ? script.Emulator.Id : ''
  const emulatorIndex = script.Emulator?.Index == null ? '' : String(script.Emulator.Index)
  if (Boolean(emulatorId) !== Boolean(emulatorIndex)) {
    throw new Error('所选脚本的模拟器绑定不完整')
  }
  if (emulatorId) {
    if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(emulatorId)) {
      throw new Error('所选脚本的模拟器 ID 无效')
    }
    if (!/^\d+$/.test(emulatorIndex)) throw new Error('模拟器实例索引必须是数字')
    if (env.AUTO_MAS_E2E_EMULATOR_ID && env.AUTO_MAS_E2E_EMULATOR_ID !== emulatorId) {
      throw new Error('所选脚本绑定的模拟器与 E2E 目标不一致')
    }
    if (env.AUTO_MAS_E2E_EMULATOR_INDEX && env.AUTO_MAS_E2E_EMULATOR_INDEX !== emulatorIndex) {
      throw new Error('所选脚本绑定的模拟器与 E2E 目标不一致')
    }
  }
  const users = selectEntry(script.SubConfigsInfo?.UserData ?? {}, userId)
  const user = users[userId]
  if (user.Info?.Name !== env.AUTO_MAS_E2E_ACCOUNT_NAME || user.Info?.Status !== true) {
    throw new Error('所选用户名称不匹配或用户未启用')
  }
  script.SubConfigsInfo.UserData = users
  delete user.Notify
  if (user.SubConfigsInfo) delete user.SubConfigsInfo.Notify_CustomWebhooks

  const targetConfig = path.join(dataRoot, 'config')
  await mkdir(targetConfig, { recursive: true })
  const selectedConfig = { ScriptConfig: scripts }
  if (emulatorId) {
    selectedConfig.EmulatorConfig = selectEntry(
      await readConfig(path.join(sourceConfig, 'EmulatorConfig.json')),
      emulatorId
    )
  }
  for (const [name, value] of Object.entries(selectedConfig)) {
    await writeFile(path.join(targetConfig, `${name}.json`), JSON.stringify(value))
  }
  if (user.Info.StageMode && !['Fixed', '-'].includes(user.Info.StageMode)) {
    const plans = selectEntry(
      await readConfig(path.join(sourceConfig, 'PlanConfig.json')),
      user.Info.StageMode
    )
    await writeFile(path.join(targetConfig, 'PlanConfig.json'), JSON.stringify(plans))
  }

  // 只复制 MAS 托管配置，不复制上次运行的 Temp 恢复事务、备份池或账号历史。
  // BetterGI 的用户配置副本由这些公开目录组成；安装根目录仍由专项配置指向本机已有安装。
  const dataOwners = scriptType === 'BetterGIConfig' ? [userId] : ['Default', userId]
  const dataDirectories =
    scriptType === 'BetterGIConfig'
      ? [
          'ConfigFile',
          'Infrastructure',
          'OneDragon',
          'ScriptGroup',
          'GlobalDomain',
          'GlobalStygian',
        ]
      : ['ConfigFile', 'Infrastructure']
  for (const owner of dataOwners) {
    for (const directory of dataDirectories) {
      const relative = path.join('data', scriptId, owner, directory)
      const source = path.join(sourceRoot, relative)
      const inspect = async folder => {
        let entries
        try {
          const details = await lstat(folder)
          if (details.isSymbolicLink() || !details.isDirectory()) {
            throw new Error(`E2E 配置目录无效: ${relative}`)
          }
          entries = await readdir(folder, { withFileTypes: true })
        } catch (error) {
          if (error.code === 'ENOENT') return false
          throw error
        }
        for (const entry of entries) {
          if (entry.isSymbolicLink()) throw new Error(`E2E 配置目录禁止链接: ${relative}`)
          if (entry.isDirectory()) await inspect(path.join(folder, entry.name))
        }
        return true
      }
      if (await inspect(source)) {
        await mkdir(path.dirname(path.join(dataRoot, relative)), { recursive: true })
        await cp(source, path.join(dataRoot, relative), { recursive: true })
      }
    }
  }
  return { emulatorId, emulatorIndex }
}

async function main() {
  const real = process.env.AUTO_MAS_E2E_REAL === '1'
  const releaseRealRunLock = real ? await acquireRealRunLock() : undefined
  let dataRoot
  try {
    dataRoot = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-'))
    let selected = { emulatorId: '', emulatorIndex: '' }
    if (real) {
      selected = await seedRealProfile(
        process.env.AUTO_MAS_E2E_TEMPLATE_ROOT ?? path.resolve(frontendRoot, '..'),
        dataRoot,
        process.env
      )
    }
    await mkdir(path.join(dataRoot, 'config'), { recursive: true })
    await writeFile(
      path.join(dataRoot, 'config', 'ToolsConfig.json'),
      JSON.stringify({ ArknightsPC: { Enabled: false } })
    )
    const cli = path.join(path.dirname(require.resolve('@playwright/test/package.json')), 'cli.js')
    const child = spawn(process.execPath, [cli, 'test', ...process.argv.slice(2)], {
      cwd: frontendRoot,
      stdio: 'inherit',
      windowsHide: true,
      env: {
        ...process.env,
        AUTO_MAS_E2E_DATA_ROOT: dataRoot,
        AUTO_MAS_E2E_EMULATOR_ID: selected.emulatorId,
        AUTO_MAS_E2E_EMULATOR_INDEX: selected.emulatorIndex,
        ...(real ? { PLAYWRIGHT_NO_COPY_PROMPT: '1' } : {}),
      },
    })
    // Playwright 先停止两个 webServer，父进程才可删除其工作目录。
    const interrupt = () => child.kill('SIGINT')
    process.on('SIGINT', interrupt)
    try {
      process.exitCode = await new Promise((resolve, reject) => {
        child.once('error', reject)
        child.once('exit', code => resolve(code ?? 1))
      })
    } finally {
      process.off('SIGINT', interrupt)
    }
  } finally {
    try {
      if (dataRoot) {
        assert(
          path.dirname(dataRoot) === path.resolve(tmpdir()) &&
            path.basename(dataRoot).startsWith('auto-mas-e2e-'),
          '拒绝清理 E2E 临时目录之外的路径'
        )
        await rm(dataRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 })
      }
    } finally {
      await releaseRealRunLock?.()
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
