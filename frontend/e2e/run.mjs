import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'
import { cp, lstat, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse, stringify } from 'yaml'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = path.resolve(frontendRoot, '..')
const require = createRequire(import.meta.url)
const isPathInside = (parent, candidate) => {
  const relative = path.relative(parent, candidate)
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative))
}
const configuredTempParent = path.resolve(tmpdir())
const tempBase = isPathInside(frontendRoot, configuredTempParent)
  ? path.dirname(repositoryRoot)
  : configuredTempParent
const supportedScriptTypes = new Set([
  'MaaConfig',
  'GeneralConfig',
  'OkwwConfig',
  'OkNteConfig',
  'SrcConfig',
  'MaaEndConfig',
  'MaaFWConfig',
  'M9AConfig',
  'HSRConfig',
  'BetterGIConfig',
  'ZzzOdConfig',
  'BAAHConfig',
  'WhimboxConfig',
  'MSSConfig',
])
const embeddedScriptTypes = new Set(['MaaFWConfig', 'M9AConfig', 'MSSConfig'])

const planSelectionByScriptType = {
  MaaConfig: { field: 'StageMode', type: 'MaaPlanConfig' },
  MaaEndConfig: { field: 'SanityMode', type: 'MaaEndPlanConfig' },
  BAAHConfig: { field: 'StageMode', type: 'BAAHPlanConfig' },
  MSSConfig: { field: 'PlanMode', type: 'MSSPlanConfig' },
}

const defaultRealRunLockPath =
  process.platform === 'win32'
    ? path.join(
        process.env.SystemRoot ?? 'C:\\Windows',
        'Temp',
        'AUTO-MAS',
        'auto-mas-e2e-real.lock'
      )
    : path.join(tempBase, 'auto-mas-e2e-real.lock')

export async function acquireRealRunLock(lockPath = defaultRealRunLockPath) {
  await mkdir(path.dirname(lockPath), { recursive: true })
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

/** 让一次 e2e 运行占用独立端口，多个运行/多人同时跑不会互相抢服务器。 */
export const pickFreePort = () =>
  new Promise((resolve, reject) => {
    const server = createServer()
    server.unref()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => (port > 0 ? resolve(port) : reject(new Error('无法分配空闲端口'))))
    })
  })

/**
 * 依赖没装时应用起不来，Playwright 只会报「找不到元素」，
 * 真正的原因（Vite 解析不到某个包）埋在页面 overlay 里，很难看出来。
 * 这里提前把话说清楚，失败原因对得上手该做的事。
 */
export const assertFrontendDependencies = async (root = frontendRoot) => {
  let packageJson
  try {
    packageJson = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'))
  } catch {
    return
  }
  const declared = Object.keys({ ...packageJson.dependencies, ...packageJson.devDependencies })
  const missing = []
  for (const name of declared) {
    try {
      await lstat(path.join(root, 'node_modules', ...name.split('/')))
    } catch {
      missing.push(name)
    }
  }
  if (missing.length > 0) {
    const preview = missing.slice(0, 5).join('、')
    throw new Error(
      `前端依赖未安装或与 package.json 不一致（缺少 ${preview}${missing.length > 5 ? ` 等 ${missing.length} 个` : ''}）。` +
        '应用因此在浏览器里起不来，所有用例都会变成「找不到元素」。先在 frontend/ 执行 yarn install 再跑测试。'
    )
  }
  try {
    const lockBytes = (await lstat(path.join(root, 'yarn.lock'))).mtimeMs
    const stateBytes = (await lstat(path.join(root, 'node_modules', '.yarn-state.yml'))).mtimeMs
    if (stateBytes + 1000 < lockBytes) {
      console.warn('[e2e] yarn.lock 比 node_modules 新：依赖可能没重装，先执行 yarn install 再跑')
    }
  } catch {
    // 没有 yarn.lock 或 state 文件时不阻塞：缺失依赖已在上面的硬检查里报出来。
  }
}

/**
 * Playwright 升级后自带的 Chromium 版本也变了，缓存里只有旧版时启动会失败：
 * 「Executable doesn't exist at ...\\chromium_headless_shell-1248\\...」——
 * 报错里只有路径，看不出要执行什么命令。这里真启动一次浏览器，
 * 用实际结果判断，再翻译成「该执行哪条命令」。
 */
export const assertPlaywrightBrowser = async (root = frontendRoot) => {
  let chromium
  try {
    const playwrightRequire = createRequire(path.join(root, 'package.json'))
    chromium = playwrightRequire('@playwright/test').chromium
  } catch (error) {
    throw new Error(
      `读不到 @playwright/test（${error instanceof Error ? error.message : String(error)}）。先在 frontend/ 执行 yarn install 再跑测试。`
    )
  }
  let browser
  try {
    browser = await chromium.launch({ headless: true })
  } catch (error) {
    const detail = error instanceof Error ? error.message.split('\n')[0] : String(error)
    const missingBinary = /Executable doesn't exist|is not found|ENOENT/i.test(detail)
    throw new Error(
      `${missingBinary ? 'Playwright 自带的浏览器还没下载' : '浏览器启动失败'}（${detail}）。` +
        '所有用例都会在启动浏览器这一步失败。先在 frontend/ 执行 yarn playwright install chromium 再跑测试。'
    )
  } finally {
    await browser?.close().catch(() => undefined)
  }
}

const configFiles = {
  ScriptConfig: 'scripts.yaml',
  EmulatorConfig: 'emulators.yaml',
  PlanConfig: 'plans.yaml',
}

// 已升级的数据根只读 YAML；旧 JSON 只用于尚未完成迁移的数据根。
const readConfig = async (directory, name) => {
  let file = path.join(directory, configFiles[name])
  let details
  try {
    details = await lstat(file)
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
    let migration
    try {
      migration = JSON.parse(
        await readFile(path.join(directory, '.config-migration-v2.json'), 'utf8')
      )
    } catch (recordError) {
      if (recordError.code !== 'ENOENT') throw recordError
    }
    if (migration?.complete === true) {
      throw new Error(`已升级的 E2E 配置缺少 ${configFiles[name]}，请先在应用中恢复配置`)
    }
    file = path.join(directory, `${name}.json`)
  }
  try {
    details ??= await lstat(file)
    if (details.isSymbolicLink() || !details.isFile()) throw new Error('invalid file')
    const text = (await readFile(file, 'utf8')).replace(/^\uFEFF/, '')
    const value = file.endsWith('.yaml') ? parse(text) : JSON.parse(text)
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('invalid document')
    }
    return value
  } catch {
    throw new Error(
      `无法读取 E2E 配置 ${path.basename(file)}：不存在、为空或格式无效。先在本机应用里配好一个用户；在 worktree 里跑时用 AUTO_MAS_E2E_TEMPLATE_ROOT 指向你的主检出目录`
    )
  }
}

export const readRealScripts = sourceRoot =>
  readConfig(path.join(path.resolve(sourceRoot), 'config'), 'ScriptConfig')

const collectionOrder = collection => collection.order ?? collection.instances ?? []
const collectionValue = (collection, id) => (collection.data ?? collection)[id]

const selectEntry = (collection, id, expectedType) => {
  const entry = collectionOrder(collection).find(item => item.uid === id)
  const value = collectionValue(collection, id)
  if (!entry || !value) throw new Error('所选 E2E 配置项不存在')
  if (expectedType && entry.type !== expectedType) {
    throw new Error(`所选 E2E 计划表类型不匹配，需要 ${expectedType}`)
  }
  return collection.order
    ? { order: [entry], data: { [id]: value } }
    : { instances: [entry], [id]: value }
}

const uuidPattern = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i
const describeSelection = candidate =>
  `${candidate.accountName}（${candidate.scriptType} 脚本 ${candidate.scriptId} / 用户 ${candidate.userId}）`

// 开发者在应用里调好的第一个已启用用户就是默认真实 E2E 目标，避免为跑一次测试再抄三个 UUID。
export const listRealCandidates = scriptConfig => {
  const candidates = []
  for (const instance of collectionOrder(scriptConfig)) {
    if (!supportedScriptTypes.has(instance.type)) continue
    const script = collectionValue(scriptConfig, instance.uid)
    const users = script?.UserData ?? script?.SubConfigsInfo?.UserData ?? {}
    for (const entry of collectionOrder(users)) {
      const info = collectionValue(users, entry.uid)?.Info
      if (info?.Status !== true || !info.Name?.trim()) continue
      candidates.push({
        scriptId: instance.uid,
        scriptType: instance.type,
        userId: entry.uid,
        accountName: info.Name,
      })
    }
  }
  return candidates
}

const resolveRealSelection = (candidates, requested) => {
  const matched = candidates.filter(
    candidate =>
      (!requested.scriptId || candidate.scriptId === requested.scriptId) &&
      (!requested.userId || candidate.userId === requested.userId) &&
      (!requested.accountName || candidate.accountName === requested.accountName)
  )
  const hint = '用 AUTO_MAS_E2E_SCRIPT_ID / AUTO_MAS_E2E_USER_ID / AUTO_MAS_E2E_ACCOUNT_NAME 指定'
  if (matched.length === 0) {
    const asked = [requested.scriptId, requested.userId, requested.accountName].filter(Boolean)
    throw new Error(
      candidates.length === 0
        ? '本机 config 里没有已启用的脚本用户；先在应用里添加一个用户，或指定 AUTO_MAS_E2E_* 变量'
        : `本机 config 里没有匹配${asked.length > 0 ? `（${asked.join(' / ')}）` : ''}的已启用用户；${hint}`
    )
  }
  if (matched.length > 1) {
    const preview = matched.slice(0, 5).map(candidate => `  - ${describeSelection(candidate)}`)
    if (matched.length > preview.length)
      preview.push(`  … 另有 ${matched.length - preview.length} 个`)
    console.warn(
      `[e2e] 本机有 ${matched.length} 个可用用户，默认用第一个：${describeSelection(matched[0])}。${hint}\n${preview.join('\n')}`
    )
  }
  return matched[0]
}

// 计划引用按分组读取：MAA 现行格式把 StageMode 放在 Stage，其余专项与旧格式在 Info。
const readPlanId = (user, field) => {
  for (const group of ['Stage', 'Info']) {
    const value = user?.[group]?.[field]
    if (typeof value === 'string' && !['Fixed', '-', ''].includes(value)) return value
  }
  return undefined
}

/**
 * 解析这一次真实 E2E 的目标脚本与用户。
 *
 * 隔离模式用它决定要往临时数据根复制什么，就地模式用它校验开发者自己的数据根；
 * 未指定 AUTO_MAS_E2E_* 时取本机第一个已启用用户。
 */
export async function resolveRealTarget(sourceRoot, env) {
  const sourceConfig = path.join(path.resolve(sourceRoot), 'config')
  const scripts = await readRealScripts(sourceRoot)
  const requested = {
    scriptId: env.AUTO_MAS_E2E_SCRIPT_ID?.trim() ?? '',
    userId: env.AUTO_MAS_E2E_USER_ID?.trim() ?? '',
    accountName: env.AUTO_MAS_E2E_ACCOUNT_NAME?.trim() ?? '',
  }
  const selection =
    requested.scriptId && requested.userId && requested.accountName
      ? requested
      : resolveRealSelection(listRealCandidates(scripts), requested)
  const problems = []
  for (const [key, value] of [
    ['SCRIPT_ID', selection.scriptId],
    ['USER_ID', selection.userId],
  ]) {
    if (!uuidPattern.test(value)) problems.push(`AUTO_MAS_E2E_${key} 必须是配置 UUID`)
  }
  if (!selection.accountName) problems.push('缺少 AUTO_MAS_E2E_ACCOUNT_NAME')
  if (problems.length > 0) throw new Error(`真实 E2E 目标配置不完整: ${problems.join('；')}`)

  const selectedScripts = selectEntry(scripts, selection.scriptId)
  const script = collectionValue(selectedScripts, selection.scriptId)
  const scriptType = collectionOrder(selectedScripts)[0].type
  if (!supportedScriptTypes.has(scriptType)) {
    throw new Error(`真实 E2E 尚未登记专项类型 ${scriptType}，请由专项作者补充适配`)
  }
  const binding = ['GeneralConfig', 'MaaEndConfig'].includes(scriptType)
    ? { Id: script.Game?.EmulatorId, Index: script.Game?.EmulatorIndex }
    : script.Emulator
  const emulatorConfigId = typeof binding?.Id === 'string' && binding.Id !== '-' ? binding.Id : ''
  // 通用脚本可保留未使用的绑定；复制引用，但只为启用了模拟器游戏的目标启动实例。
  const usesEmulator =
    scriptType !== 'GeneralConfig' ||
    (script.Game?.Enabled === true && script.Game?.Type === 'Emulator')
  const emulatorId = usesEmulator ? emulatorConfigId : ''
  const emulatorIndex =
    !usesEmulator || binding?.Index == null || binding.Index === '-' ? '' : String(binding.Index)
  if (Boolean(emulatorId) !== Boolean(emulatorIndex)) {
    throw new Error('所选脚本的模拟器绑定不完整')
  }
  if (emulatorId) {
    if (!uuidPattern.test(emulatorId)) throw new Error('所选脚本的模拟器 ID 无效')
    if (!/^\d+$/.test(emulatorIndex)) throw new Error('模拟器实例索引必须是数字')
    if (env.AUTO_MAS_E2E_EMULATOR_ID && env.AUTO_MAS_E2E_EMULATOR_ID !== emulatorId) {
      throw new Error('所选脚本绑定的模拟器与 E2E 目标不一致')
    }
    if (env.AUTO_MAS_E2E_EMULATOR_INDEX && env.AUTO_MAS_E2E_EMULATOR_INDEX !== emulatorIndex) {
      throw new Error('所选脚本绑定的模拟器与 E2E 目标不一致')
    }
  }
  return {
    sourceConfig,
    scripts: selectedScripts,
    script,
    scriptType,
    emulatorConfigId,
    emulatorId,
    emulatorIndex,
    scriptId: selection.scriptId,
    userId: selection.userId,
    accountName: selection.accountName,
  }
}

export async function seedRealProfile(sourceRoot, dataRoot, env) {
  sourceRoot = path.resolve(sourceRoot)
  const resolved = await resolveRealTarget(sourceRoot, env)
  const {
    sourceConfig,
    scripts,
    script,
    scriptType,
    emulatorConfigId,
    emulatorId,
    emulatorIndex,
    scriptId,
    userId,
  } = resolved
  const users = selectEntry(script.UserData ?? script.SubConfigsInfo?.UserData ?? {}, userId)
  const user = collectionValue(users, userId)
  if (user.Info?.Name !== resolved.accountName || user.Info?.Status !== true) {
    throw new Error('所选用户名称不匹配或用户未启用')
  }
  if (script.UserData) script.UserData = users
  else script.SubConfigsInfo.UserData = users
  // 移除所有通知配置，避免测试发送真实通知
  for (const key of Object.keys(user)) {
    if (key.includes('Notify')) delete user[key]
  }
  if (user.SubConfigsInfo) {
    for (const key of Object.keys(user.SubConfigsInfo)) {
      if (key.includes('Notify')) delete user.SubConfigsInfo[key]
    }
  }

  const targetConfig = path.join(dataRoot, 'config')
  await mkdir(targetConfig, { recursive: true })
  const selectedConfig = { ScriptConfig: scripts }
  if (emulatorConfigId) {
    selectedConfig.EmulatorConfig = selectEntry(
      await readConfig(sourceConfig, 'EmulatorConfig'),
      emulatorConfigId
    )
  }
  const planSelection = planSelectionByScriptType[scriptType]
  const planId = planSelection ? readPlanId(user, planSelection.field) : undefined
  if (planSelection && planId) {
    const plans = selectEntry(
      await readConfig(sourceConfig, 'PlanConfig'),
      planId,
      planSelection.type
    )
    selectedConfig.PlanConfig = plans
  }
  // 保留输入格式；只复制选中条目，不把当前配置重新降为旧格式再迁移。
  const yaml = Array.isArray(scripts.order)
  for (const [name, value] of Object.entries(selectedConfig)) {
    if (Array.isArray(value.order) !== yaml) {
      throw new Error('E2E 配置迁移尚未完成，请先正常启动应用完成迁移')
    }
    await writeFile(
      path.join(targetConfig, yaml ? configFiles[name] : `${name}.json`),
      yaml ? stringify(value) : JSON.stringify(value, null, 2)
    )
  }
  if (yaml) {
    // 当前 YAML 的隔离副本从 v2.0 启动，避免首次启动再次尝试 JSON 迁移。
    const { DatabaseSync } = await import('node:sqlite')
    await mkdir(path.join(dataRoot, 'data'), { recursive: true })
    const database = new DatabaseSync(path.join(dataRoot, 'data', 'data.db'))
    try {
      database.exec("CREATE TABLE version(v TEXT); INSERT INTO version VALUES('v2.0');")
    } finally {
      database.close()
    }
  }

  // 只复制 MAS 托管配置，不复制上次运行的 Temp 恢复事务、备份池或账号历史。
  // BetterGI 的用户配置副本由这些公开目录组成；安装根目录仍由专项配置指向本机已有安装。
  const copyDirectory = async relative => {
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
    if (!(await inspect(source))) return false
    const target = path.join(dataRoot, relative)
    await mkdir(path.dirname(target), { recursive: true })
    await cp(source, target, { recursive: true })
    return true
  }

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
      await copyDirectory(path.join('data', scriptId, owner, directory))
    }
  }
  if (embeddedScriptTypes.has(scriptType)) {
    await copyDirectory(
      path.join('data', 'mfw', scriptId.replaceAll('-', '').toLowerCase().slice(0, 12))
    )
  }
  if (scriptType === 'HSRConfig' && script.Game?.Platform === 'Cloud') {
    await copyDirectory(path.join('data', scriptId, userId, 'cloud-profile'))
  }
  return {
    emulatorId,
    emulatorIndex,
    scriptId,
    userId,
    accountName: resolved.accountName,
  }
}

export function parseLauncherArgs(argv, env = process.env) {
  return {
    inPlace: argv.includes('--in-place') || env.AUTO_MAS_E2E_IN_PLACE === '1',
    playwrightArgs: argv.filter(argument => argument !== '--in-place'),
  }
}

async function main() {
  const real = process.env.AUTO_MAS_E2E_REAL === '1'
  const { inPlace, playwrightArgs } = parseLauncherArgs(process.argv.slice(2))
  const keepRoot = process.env.AUTO_MAS_E2E_KEEP_ROOT === '1'
  const releaseRealRunLock = real ? await acquireRealRunLock() : undefined
  let dataRoot
  let runRoot
  try {
    // 依赖不全时应用根本起不来，先在这里失败，避免十几条用例一起报「找不到元素」
    if (!real) await assertFrontendDependencies()
    // 浏览器没装时每条用例都会在启动阶段失败，先在这里说清楚要执行什么
    await assertPlaywrightBrowser()
    await mkdir(tempBase, { recursive: true })
    runRoot = await mkdtemp(path.join(tempBase, 'auto-mas-e2e-'))
    const tempDirectory = path.join(runRoot, 'temp')
    await mkdir(tempDirectory, { recursive: true })
    let selected = { emulatorId: '', emulatorIndex: '', scriptId: '', userId: '', accountName: '' }
    if (inPlace) {
      // 就地模式：直接用开发者自己调好的配置，方便顺手调试要接入的字段，跑完不清理
      dataRoot = path.resolve(process.env.AUTO_MAS_E2E_DATA_ROOT?.trim() || repositoryRoot)
      if (real) {
        // 就地真实运行同样要确认目标；不解析就会把空值传下去，让 spec 静默 skip 整条流程
        selected = await resolveRealTarget(dataRoot, process.env)
        console.warn(
          `[e2e] 真实 E2E 目标：${selected.accountName}（脚本 ${selected.scriptId} / 用户 ${selected.userId}）`
        )
      }
      console.warn(
        `[e2e] 就地数据根 ${dataRoot}：测试会写入它的 config/data/history/debug 且不清理`
      )
    } else {
      dataRoot = path.join(runRoot, 'data')
      if (real) {
        selected = await seedRealProfile(
          process.env.AUTO_MAS_E2E_TEMPLATE_ROOT ?? repositoryRoot,
          dataRoot,
          process.env
        )
        console.warn(
          `[e2e] 真实 E2E 目标：${selected.accountName}（脚本 ${selected.scriptId} / 用户 ${selected.userId}）`
        )
      }
      // 其他配置由隔离根按默认值新建，不复制本机工具、签到账号或启动队列。
      await mkdir(path.join(dataRoot, 'config'), { recursive: true })
      console.warn(`[e2e] 隔离数据根 ${dataRoot}${keepRoot ? '（跑完保留）' : '（跑完删除）'}`)
    }
    // 真实模式以所选配置为准，清空未使用的模拟器变量，避免沿用上次运行的目标。
    const selectedEnv = Object.fromEntries(
      Object.entries({
        SCRIPT_ID: selected.scriptId,
        USER_ID: selected.userId,
        ACCOUNT_NAME: selected.accountName,
        EMULATOR_ID: selected.emulatorId,
        EMULATOR_INDEX: selected.emulatorIndex,
      })
        .filter(([, value]) => real || value)
        .map(([key, value]) => [`AUTO_MAS_E2E_${key}`, value])
    )
    // 端口与产物目录都按这次运行独立：并行跑同一条用例时不会抢 webServer，也不会互相覆盖报告
    const ports = {
      AUTO_MAS_E2E_BACKEND_PORT: process.env.AUTO_MAS_E2E_BACKEND_PORT?.trim() ?? '',
      AUTO_MAS_E2E_FRONTEND_PORT: process.env.AUTO_MAS_E2E_FRONTEND_PORT?.trim() ?? '',
    }
    if (!ports.AUTO_MAS_E2E_BACKEND_PORT)
      ports.AUTO_MAS_E2E_BACKEND_PORT = String(await pickFreePort())
    if (!ports.AUTO_MAS_E2E_FRONTEND_PORT) {
      let candidate = await pickFreePort()
      while (String(candidate) === ports.AUTO_MAS_E2E_BACKEND_PORT) candidate = await pickFreePort()
      ports.AUTO_MAS_E2E_FRONTEND_PORT = String(candidate)
    }
    const runTag =
      process.env.AUTO_MAS_E2E_RUN_TAG?.trim() ||
      path.basename(runRoot).replace(/^auto-mas-e2e-/, '')
    console.warn(
      `[e2e] 后端 ${ports.AUTO_MAS_E2E_BACKEND_PORT} / 前端 ${ports.AUTO_MAS_E2E_FRONTEND_PORT}，产物目录 ${runTag}`
    )
    const cli = path.join(path.dirname(require.resolve('@playwright/test/package.json')), 'cli.js')
    const child = spawn(process.execPath, [cli, 'test', ...playwrightArgs], {
      cwd: frontendRoot,
      stdio: 'inherit',
      windowsHide: true,
      env: {
        ...process.env,
        TEMP: tempDirectory,
        TMP: tempDirectory,
        TMPDIR: tempDirectory,
        AUTO_MAS_E2E_DATA_ROOT: dataRoot,
        AUTO_MAS_E2E_RUN_TAG: runTag,
        ...ports,
        ...selectedEnv,
        AUTO_MAS_E2E_IN_PLACE: inPlace ? '1' : '',
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
      if (runRoot && keepRoot) {
        console.warn(`[e2e] 已保留数据根：${dataRoot}`)
      } else if (runRoot) {
        assert(
          path.dirname(runRoot) === tempBase &&
            path.basename(runRoot).startsWith('auto-mas-e2e-') &&
            !isPathInside(frontendRoot, runRoot),
          '拒绝清理 E2E 临时目录之外的路径'
        )
        await rm(runRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 })
      }
    } finally {
      await releaseRealRunLock?.()
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
