import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  addDebugDirectory,
  addDiagnosticFile,
  addDirectory,
  addReportManifest,
  addSanitizedJsonFile,
  addSanitizedJsonValue,
  isRecord,
  readJson,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('MFW问题包')

// 与 app/models/config.py 的 M9AConfig 类名同步
const M9A_CONFIG_TYPE = 'M9AConfig'

// 与 app/task/MaaFW/tools/embedded/embedded_project.py 的 embedded_copy_dir_name 同步：
// 每个脚本的项目视图是 data/mfw/<脚本 uuid 去掉连字符的前 12 位>/
const VIEW_DIR_NAME_LENGTH = 12

// 与 app/task/MaaFW/tools/embedded/runner_task.py 的 history_dir / history_stamp 同步：
// history/<YYYY-MM-DD>/<用户名>/<HH-MM-SS>.{json,log,worker.log,maafw.log}，
// 失败截图 <HH-MM-SS>.<failed|timeout>-<HHMMSS>-<任务名>.png 与它们放在一起
const HISTORY_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const HISTORY_FILE_PATTERN = /^(\d{2}-\d{2}-\d{2})\.(.+)$/
const SCREENSHOT_SUFFIX_PATTERN = /^[a-z]+-\d{6}-.+\.png$/i
const HISTORY_SCAN_DAYS = 30
const RECENT_RUN_COUNT = 5
const RECENT_FAILED_RUN_COUNT = 3

// 一次运行的原生日志副本（.maafw.log）实测 20–60 MB，按其他专项的 25 MB 单文件上限只能留一半；
// 文本压缩比在 10 倍以上，放宽到 64 MB / 160 MB 后实测压缩包 11–18 MB
const MAX_ENTRY_BYTES = 64 * 1024 * 1024
const MAX_ARCHIVE_BYTES = 160 * 1024 * 1024

// history 目录按用户名分，不同脚本的同名用户会落进同一个目录。.worker.log 开头几行就有项目
// 路径（MaaFramework 加载来源、资源路径），按它认领运行记录，改过用户名的旧记录也认得出。
// 有视图之前的版本直接在导入来源（Info.Path）里跑，那时的记录按来源路径认
const VIEW_PATH_PATTERN = /[\\/]mfw[\\/]([0-9a-f]{12})(?![0-9a-f])/i
const WORKER_LOG_HEAD_BYTES = 64 * 1024
const RUN_LOG_HEAD_BYTES = 64 * 1024
const MAAFW_RUN_LOG_MARKER = /MaaFW|MFW/

// PI v2.10.0 的 password 输入框：MaaFramework 会把 override 连同密码原文写进项目自己的
// debug 日志（见 app/task/MaaFW/AGENTS.md）；MAS 只给 history 副本里 4 个字符以上的密码打码，
// v5.6.0-beta.1 之前的副本则完全没打。interface 允许 JSON5，键名可以不带引号
const PASSWORD_INPUT_PATTERN = /["']?password["']?\s*:\s*true/
const IMPORT_LIST_PATTERN = /["']?import["']?\s*:\s*\[([^\]]*)\]/g
const STRING_LITERAL_PATTERN = /"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'/g
const MAX_INTERFACE_FILES = 64
const SEALED_SECRET_PREFIX = 'mas-dpapi:'
// 与 app/task/MaaFW/tools/embedded/option_secrets.py 的 LOG_REDACTION_MARKER 同步：有 password
// 输入框的项目每次运行的 .worker.log 第一行以它开头，说明这次的 .worker.log / .maafw.log 写的时候
// 就打过码
const LOG_REDACTION_MARKER = '[MAS 日志打码]'
const SEALED_SECRET_PATTERN = /mas-dpapi:[^"'\\\s]*/g

// 通用脱敏之外，脚本配置里还要去掉的：通知渠道整段不收；账号、备注、游戏启动参数、
// 前后置脚本、Mirror 酱 CDK、可能带账密的代理地址打码
const DROPPED_CONFIG_KEYS = new Set(['Notify'])
const MASKED_CONFIG_KEY_PATTERN =
  /^(?:Account|Notes|Arguments|ScriptBeforeTask|ScriptAfterTask|ProxyAddress)$|cdk/i

export interface MaaFWIssueReportScript {
  uid: string
  /** ScriptConfig.json 里的配置类名，如 'MaaFWConfig' / 'M9AConfig' */
  type: string
  name: string
  projectLabel: string
}

interface MaaFWScript extends MaaFWIssueReportScript {
  dataRoot: string
  viewDirName: string
  config: Record<string, unknown>
  userNames: string[]
}

interface HistoryRun {
  date: string
  user: string
  stamp: string
  json?: string
  log?: string
  workerLog?: string
  maafwLog?: string
  screenshots: string[]
  /** .worker.log 里认出的项目视图；null 表示读过但没认出来 */
  viewDirName?: string | null
}

interface SelectedRun {
  run: HistoryRun
  result?: string
  success: boolean
  matchedBy: 'projectPath' | 'userName'
}

interface IssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

function viewDirNameOf(scriptId: string): string | undefined {
  const hex = scriptId.trim().replace(/-/g, '').toLowerCase()
  return /^[0-9a-f]{32}$/.test(hex) ? hex.slice(0, VIEW_DIR_NAME_LENGTH) : undefined
}

/** 路径比较用的形式：小写、正斜杠、无结尾斜杠。 */
function pathKey(value: string): string {
  return value.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
}

function stringField(section: unknown, key: string): string {
  return isRecord(section) && typeof section[key] === 'string'
    ? (section[key] as string).trim()
    : ''
}

function readDirectory(dir: string): fs.Dirent[] {
  try {
    return fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return []
  }
}

function readHead(filePath: string, bytes: number): string {
  let fd: number | undefined
  try {
    fd = fs.openSync(filePath, 'r')
    const buffer = Buffer.alloc(bytes)
    const read = fs.readSync(fd, buffer, 0, bytes, 0)
    return buffer.subarray(0, read).toString('utf-8')
  } catch (error) {
    logger.debug(`读取文件开头失败: ${filePath}, ${String(error)}`)
    return ''
  } finally {
    if (fd !== undefined) {
      try {
        fs.closeSync(fd)
      } catch {
        // 只读句柄，关不掉也不影响导出
      }
    }
  }
}

function isInside(parent: string, target: string): boolean {
  const relative = path.relative(parent, target)
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative)
}

function userNamesOf(config: Record<string, unknown>): string[] {
  const subConfigs = config.SubConfigsInfo
  const userData = isRecord(subConfigs) ? subConfigs.UserData : undefined
  if (!isRecord(userData) || !Array.isArray(userData.instances)) {
    return []
  }

  const names = new Set<string>()
  for (const instance of userData.instances) {
    const uid = isRecord(instance) && typeof instance.uid === 'string' ? instance.uid : ''
    const user = uid ? userData[uid] : undefined
    const name = isRecord(user) ? stringField(user.Info, 'Name') : ''
    if (name) {
      names.add(name)
    }
  }
  return [...names]
}

function discoverMaaFWScripts(
  dataRoots: string[],
  accept: (uid: string, type: string) => boolean
): MaaFWScript[] {
  const scripts: MaaFWScript[] = []
  const seenUids = new Set<string>()

  for (const dataRoot of dataRoots) {
    const scriptConfig = readJson(path.join(dataRoot, 'config', 'ScriptConfig.json'))
    if (!isRecord(scriptConfig) || !Array.isArray(scriptConfig.instances)) {
      continue
    }

    for (const instance of scriptConfig.instances) {
      if (!isRecord(instance)) {
        continue
      }
      const uid = typeof instance.uid === 'string' ? instance.uid : ''
      const type = typeof instance.type === 'string' ? instance.type : ''
      const viewDirName = viewDirNameOf(uid)
      const config = scriptConfig[uid]
      if (!viewDirName || !isRecord(config) || seenUids.has(uid) || !accept(uid, type)) {
        continue
      }

      seenUids.add(uid)
      scripts.push({
        uid,
        type,
        name: stringField(config.Info, 'Name') || uid,
        projectLabel: stringField(config.Info, 'ProjectLabel'),
        dataRoot,
        viewDirName,
        config,
        userNames: userNamesOf(config),
      })
    }
  }

  return scripts
}

/** 设置页下拉用：列出指定配置类的脚本（配置类名由前端特调注册表给出）。 */
export function listMaaFWIssueReportScripts(
  appRoot: string,
  configTypes: string[]
): MaaFWIssueReportScript[] {
  const accepted = new Set(configTypes)
  return discoverMaaFWScripts(resolveDataRoots(appRoot), (_uid, type) => accepted.has(type)).map(
    ({ uid, type, name, projectLabel }) => ({ uid, type, name, projectLabel })
  )
}

function findMaaFWScript(appRoot: string, scriptId: string): MaaFWScript | undefined {
  return discoverMaaFWScripts(resolveDataRoots(appRoot), uid => uid === scriptId)[0]
}

/** 问题包默认文件名前缀：带上脚本名，一眼能看出是哪个脚本的包。 */
export function maafwIssueReportFileNamePrefix(appRoot: string, scriptId: string): string {
  const name = findMaaFWScript(appRoot, scriptId)?.name ?? ''
  const safeName = name
    .replace(/[\\/:*?"<>|\s]+/g, '_')
    .replace(/^[._]+|[._]+$/g, '')
    .slice(0, 40)
  return safeName ? `MFW-${safeName}-logs` : 'MFW-logs'
}

function scanHistoryRuns(dataRoot: string): HistoryRun[] {
  const historyRoot = path.join(dataRoot, 'history')
  const dates = readDirectory(historyRoot)
    .filter(entry => entry.isDirectory() && HISTORY_DATE_PATTERN.test(entry.name))
    .map(entry => entry.name)
    .sort()
    .reverse()
    .slice(0, HISTORY_SCAN_DAYS)

  const runs: HistoryRun[] = []
  for (const date of dates) {
    for (const userEntry of readDirectory(path.join(historyRoot, date))) {
      if (!userEntry.isDirectory()) {
        continue
      }

      const userDir = path.join(historyRoot, date, userEntry.name)
      const runsByStamp = new Map<string, HistoryRun>()
      for (const fileEntry of readDirectory(userDir)) {
        const match = fileEntry.isFile() ? HISTORY_FILE_PATTERN.exec(fileEntry.name) : null
        if (!match) {
          continue
        }

        const [, stamp, suffix] = match
        const run = runsByStamp.get(stamp) ?? {
          date,
          user: userEntry.name,
          stamp,
          screenshots: [],
        }
        const filePath = path.join(userDir, fileEntry.name)
        switch (suffix.toLowerCase()) {
          case 'json':
            run.json = filePath
            break
          case 'log':
            run.log = filePath
            break
          case 'worker.log':
            run.workerLog = filePath
            break
          case 'maafw.log':
            run.maafwLog = filePath
            break
          default:
            if (!SCREENSHOT_SUFFIX_PATTERN.test(suffix)) {
              continue
            }
            run.screenshots.push(filePath)
        }
        runsByStamp.set(stamp, run)
      }
      runs.push(...runsByStamp.values())
    }
  }

  return runs.sort((left, right) =>
    `${right.date} ${right.stamp}`.localeCompare(`${left.date} ${left.stamp}`)
  )
}

function workerLogViewDirName(run: HistoryRun): string | null {
  if (run.viewDirName === undefined) {
    const head = run.workerLog ? readHead(run.workerLog, WORKER_LOG_HEAD_BYTES) : ''
    run.viewDirName = VIEW_PATH_PATTERN.exec(head)?.[1]?.toLowerCase() ?? null
  }
  return run.viewDirName
}

function workerLogRedactedAtWrite(run: HistoryRun): boolean {
  if (!run.workerLog) {
    return false
  }
  const [firstLine] = readHead(run.workerLog, WORKER_LOG_HEAD_BYTES).split('\n', 1)
  return firstLine.includes(LOG_REDACTION_MARKER)
}

function readRunResult(run: HistoryRun): string | undefined {
  const data = run.json ? readJson(run.json) : undefined
  return isRecord(data) && typeof data.general_result === 'string' ? data.general_result : undefined
}

// 与 app/core/config.py search_history 里的 is_success_result 同步
function isSuccessResult(result: string | undefined): boolean {
  if (result === undefined) {
    return false
  }
  const value = result.replace(/^\[[^\]]+\]\s*/, '')
  return value === 'Success!' || value === '今日任务均已完成'
}

/** 同一数据根下所有脚本（不限类型）的导入来源，用来认没有视图路径的旧记录。 */
function sourcePathKeysOf(dataRoot: string): Array<{ uid: string; key: string }> {
  const scriptConfig = readJson(path.join(dataRoot, 'config', 'ScriptConfig.json'))
  if (!isRecord(scriptConfig) || !Array.isArray(scriptConfig.instances)) {
    return []
  }
  return scriptConfig.instances.flatMap(instance => {
    const uid = isRecord(instance) && typeof instance.uid === 'string' ? instance.uid : ''
    const config = uid ? scriptConfig[uid] : undefined
    const key = isRecord(config) ? pathKey(stringField(config.Info, 'Path')) : ''
    return key ? [{ uid, key }] : []
  })
}

function claimRun(
  run: HistoryRun,
  script: MaaFWScript,
  result: string | undefined,
  sourceKeys: Array<{ uid: string; key: string }>
): SelectedRun['matchedBy'] | undefined {
  const viewDirName = workerLogViewDirName(run)
  if (viewDirName) {
    return viewDirName === script.viewDirName ? 'projectPath' : undefined
  }
  if (run.workerLog) {
    // 几个脚本的来源互相包含时，最长的那个才是这次运行的项目；一样长（同一个来源）都算
    const head = pathKey(readHead(run.workerLog, WORKER_LOG_HEAD_BYTES))
    const owners = sourceKeys.filter(({ key }) => head.includes(`${key}/`))
    const longest = Math.max(0, ...owners.map(({ key }) => key.length))
    if (owners.length > 0) {
      return owners.some(({ uid, key }) => uid === script.uid && key.length === longest)
        ? 'projectPath'
        : undefined
    }
  }

  // 认不出项目路径——worker 没起来（模拟器没起来、环境准备或项目更新失败）就没有 .worker.log，
  // 或者 worker 在打出加载来源之前就挂了——只能按脚本现有的用户名认领；同名用户的其他 MFW
  // 脚本的这类记录会一并带上
  if (result === undefined || !run.log || !script.userNames.includes(run.user)) {
    return undefined
  }
  return MAAFW_RUN_LOG_MARKER.test(readHead(run.log, RUN_LOG_HEAD_BYTES)) ? 'userName' : undefined
}

/** 最近 RECENT_RUN_COUNT 次运行，外加最近 RECENT_FAILED_RUN_COUNT 次失败，新的在前。 */
function selectRuns(
  runs: HistoryRun[],
  script: MaaFWScript,
  sourceKeys: Array<{ uid: string; key: string }>
): SelectedRun[] {
  const selected: SelectedRun[] = []
  let claimedCount = 0
  let failedCount = 0

  for (const run of runs) {
    if (claimedCount >= RECENT_RUN_COUNT && failedCount >= RECENT_FAILED_RUN_COUNT) {
      break
    }

    const result = readRunResult(run)
    const matchedBy = claimRun(run, script, result, sourceKeys)
    if (!matchedBy) {
      continue
    }

    const success = isSuccessResult(result)
    if (claimedCount < RECENT_RUN_COUNT || (!success && failedCount < RECENT_FAILED_RUN_COUNT)) {
      selected.push({ run, result, success, matchedBy })
    }
    claimedCount += 1
    if (!success) {
      failedCount += 1
    }
  }

  return selected
}

function projectDeclaresPasswordInput(viewDir: string): boolean {
  const pending = [path.join(viewDir, 'interface.json')]
  const visited = new Set<string>()

  while (pending.length > 0 && visited.size < MAX_INTERFACE_FILES) {
    const filePath = pending.pop() as string
    const key = process.platform === 'win32' ? filePath.toLowerCase() : filePath
    if (visited.has(key)) {
      continue
    }
    visited.add(key)

    let text: string
    try {
      text = fs.readFileSync(filePath, 'utf-8')
    } catch {
      continue
    }
    if (PASSWORD_INPUT_PATTERN.test(text)) {
      return true
    }

    for (const importList of text.matchAll(IMPORT_LIST_PATTERN)) {
      for (const [, doubleQuoted, singleQuoted] of importList[1].matchAll(STRING_LITERAL_PATTERN)) {
        const importPath = (doubleQuoted ?? singleQuoted ?? '').replace(/\\(.)/g, '$1')
        const target = path.resolve(path.dirname(filePath), importPath)
        if (importPath && isInside(viewDir, target)) {
          pending.push(target)
        }
      }
    }
  }

  return false
}

function maskStringLeaves(value: unknown): unknown {
  if (typeof value === 'string') {
    return value ? '***' : value
  }
  if (Array.isArray(value)) {
    return value.map(item => maskStringLeaves(item))
  }
  return isRecord(value)
    ? Object.fromEntries(Object.entries(value).map(([key, item]) => [key, maskStringLeaves(item)]))
    : value
}

// taskOptions 是 {任务实例: {option: 值}}，input 类型 option 的值是 {字段: 值}。旧版本存下的
// 密码是明文（下次保存才加密），项目有 password 输入框时 input 的值一律打码
function maskInputOptionValues(taskOptions: unknown): unknown {
  if (!isRecord(taskOptions)) {
    return taskOptions
  }
  return Object.fromEntries(
    Object.entries(taskOptions).map(([task, options]) => [
      task,
      isRecord(options)
        ? Object.fromEntries(
            Object.entries(options).map(([name, item]) => [
              name,
              isRecord(item) ? maskStringLeaves(item) : item,
            ])
          )
        : options,
    ])
  )
}

function redactScriptConfig(value: unknown, maskInputOptions: boolean): unknown {
  if (typeof value === 'string') {
    // TaskSnapshot 这类 JSON 字段在配置里存成字符串，拆开处理，里面的密文才打得到
    const trimmed = value.trim()
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        return redactScriptConfig(JSON.parse(trimmed), maskInputOptions)
      } catch {
        // 不是 JSON，按普通字符串处理
      }
    }
    return value.replace(SEALED_SECRET_PATTERN, '***')
  }
  if (Array.isArray(value)) {
    return value.map(item => redactScriptConfig(item, maskInputOptions))
  }
  if (!isRecord(value)) {
    return value
  }

  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !DROPPED_CONFIG_KEYS.has(key))
      .map(([key, item]) => {
        if (MASKED_CONFIG_KEY_PATTERN.test(key) && typeof item === 'string' && item) {
          return [key, '***']
        }
        const redacted = redactScriptConfig(item, maskInputOptions)
        return [
          key,
          maskInputOptions && key === 'taskOptions' ? maskInputOptionValues(redacted) : redacted,
        ]
      })
  )
}

function readViewVersion(viewDir: string): string {
  return stringField(readJson(path.join(viewDir, '.auto_mas_view.json')), 'version')
}

// 大文件要读进来逐段脱敏，同步做完才返回会卡住主进程（窗口拖不动、久了系统判定未响应），
// 每收一个大文件让一次事件循环
function yieldToEventLoop(): Promise<void> {
  return new Promise(resolve => setImmediate(resolve))
}

async function addProjectDebugDirectory(
  state: CollectorState,
  viewDir: string,
  archiveRoot: string
): Promise<void> {
  const debugDir = path.join(viewDir, 'debug')
  for (const entry of readDirectory(debugDir).sort((left, right) =>
    left.name.localeCompare(right.name)
  )) {
    const sourcePath = path.join(debugDir, entry.name)
    const archivePath = path.posix.join(archiveRoot, entry.name)
    if (entry.isDirectory()) {
      addDirectory(state, sourcePath, archivePath)
    } else if (entry.isFile() && !/^maafw(?:\.bak\..+)?\.log$/i.test(entry.name)) {
      // 顶层的 maafw.log / maafw.bak.*.log 就是 history 里各次 .maafw.log 的来源，
      // 那边已按次切好并打过码，这里不再收原文
      addDiagnosticFile(state, sourcePath, archivePath)
    }
    await yieldToEventLoop()
  }
}

async function addMasDebugLogs(state: CollectorState, dataRoots: string[]): Promise<void> {
  for (const [index, dataRoot] of dataRoots.entries()) {
    addDebugDirectory(
      state,
      path.join(dataRoot, 'debug'),
      index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend'
    )
    await yieldToEventLoop()
  }

  const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
  const knownDebugDirs = new Set(dataRoots.map(dataRoot => path.resolve(dataRoot, 'debug')))
  if (!knownDebugDirs.has(path.resolve(runtimeDebugDir))) {
    addDirectory(state, runtimeDebugDir, 'logs/frontend-runtime')
  }
}

function historyArchivePath(scriptRoot: string, run: HistoryRun, filePath: string): string {
  return path.posix.join(scriptRoot, 'history', run.date, run.user, path.basename(filePath))
}

async function addRunHeavyFiles(
  state: CollectorState,
  scriptRoot: string,
  selected: SelectedRun,
  includeNativeLog: boolean
): Promise<void> {
  const { run } = selected
  if (run.maafwLog && includeNativeLog) {
    addDiagnosticFile(state, run.maafwLog, historyArchivePath(scriptRoot, run, run.maafwLog))
    await yieldToEventLoop()
  }
  for (const screenshot of [...run.screenshots].sort()) {
    addDiagnosticFile(state, screenshot, historyArchivePath(scriptRoot, run, screenshot))
  }
}

function runOrderKey({ run }: SelectedRun): string {
  return `${run.date} ${run.stamp}`
}

/**
 * 收集顺序就是问题包总大小受限时的取舍顺序（先收的先占额度，后面的被截断或跳过）：
 * 1. 各脚本的配置、项目版本与 interface、选中运行的文本日志（.json / .log / .worker.log）
 * 2. 各脚本最近一次失败（没有失败就是最近一次）运行的原生日志副本与失败截图
 * 3. MAS 自己的日志目录
 * 4. 项目自己的 debug 目录（agent、项目自定义日志等）
 * 5. 其余选中运行的原生日志副本与失败截图：失败的在前，同类新的在前
 */
async function createIssueReport(
  appRoot: string,
  zipPath: string,
  scripts: MaaFWScript[],
  label: string
): Promise<IssueReportResult> {
  const zip = new AdmZip()
  const state: CollectorState = {
    zip,
    entries: [],
    archiveBytes: 0,
    maxEntryBytes: MAX_ENTRY_BYTES,
    maxArchiveBytes: MAX_ARCHIVE_BYTES,
  }
  const dataRoots = resolveDataRoots(appRoot)
  const runsByDataRoot = new Map<string, HistoryRun[]>()
  const sourceKeysByDataRoot = new Map<string, Array<{ uid: string; key: string }>>()
  const manifestScripts: Record<string, unknown>[] = []
  const deferred: Array<{
    scriptRoot: string
    selected: SelectedRun
    includeNativeLog: boolean
  }> = []
  const projectDebugDirs: Array<{ viewDir: string; archiveRoot: string }> = []

  for (const script of scripts) {
    const scriptRoot = `scripts/${script.viewDirName}`
    const viewDir = path.join(script.dataRoot, 'data', 'mfw', script.viewDirName)
    if (!runsByDataRoot.has(script.dataRoot)) {
      runsByDataRoot.set(script.dataRoot, scanHistoryRuns(script.dataRoot))
      sourceKeysByDataRoot.set(script.dataRoot, sourcePathKeysOf(script.dataRoot))
    }
    const selectedRuns = selectRuns(
      runsByDataRoot.get(script.dataRoot) ?? [],
      script,
      sourceKeysByDataRoot.get(script.dataRoot) ?? []
    )
    // 项目有 password 输入框（或配置里已经有加密的密码值）时，日志里可能有密码原文，
    // 脚本配置里 input 选项的值也打码
    const protectSecrets =
      JSON.stringify(script.config).includes(SEALED_SECRET_PREFIX) ||
      projectDeclaresPasswordInput(viewDir)

    addSanitizedJsonValue(
      state,
      redactScriptConfig(script.config, protectSecrets),
      `${scriptRoot}/script-config.json`
    )
    addSanitizedJsonFile(
      state,
      path.join(viewDir, '.auto_mas_view.json'),
      `${scriptRoot}/project/.auto_mas_view.json`
    )
    addDiagnosticFile(
      state,
      path.join(viewDir, 'interface.json'),
      `${scriptRoot}/project/interface.json`
    )
    for (const entry of readDirectory(path.join(viewDir, 'config'))) {
      if (entry.isFile() && path.extname(entry.name).toLowerCase() === '.json') {
        addSanitizedJsonFile(
          state,
          path.join(viewDir, 'config', entry.name),
          `${scriptRoot}/project/config/${entry.name}`
        )
      }
    }

    // 有 password 输入框的项目，.worker.log / .maafw.log 只收写的时候就打过码的那些
    // （.worker.log 第一行是打码说明）；更早版本写的副本可能是原文
    const frameworkLogsShareable = new Map(
      selectedRuns.map(selected => [
        selected,
        !protectSecrets || workerLogRedactedAtWrite(selected.run),
      ])
    )

    for (const selected of selectedRuns) {
      const { run } = selected
      const workerLog = frameworkLogsShareable.get(selected) ? run.workerLog : undefined
      for (const filePath of [run.json, run.log, workerLog]) {
        if (filePath) {
          addDiagnosticFile(state, filePath, historyArchivePath(scriptRoot, run, filePath))
        }
      }
    }

    const focusRun = selectedRuns.find(selected => !selected.success) ?? selectedRuns[0]
    if (focusRun) {
      await addRunHeavyFiles(state, scriptRoot, focusRun, !!frameworkLogsShareable.get(focusRun))
    }
    deferred.push(
      ...selectedRuns
        .filter(selected => selected !== focusRun)
        .map(selected => ({
          scriptRoot,
          selected,
          includeNativeLog: !!frameworkLogsShareable.get(selected),
        }))
    )

    // 项目 debug 目录是框架和 agent 自己写的，MAS 打不了码
    if (!protectSecrets) {
      projectDebugDirs.push({ viewDir, archiveRoot: `${scriptRoot}/project/debug` })
    }

    manifestScripts.push({
      uid: script.uid,
      type: script.type,
      name: script.name,
      projectLabel: script.projectLabel,
      archiveRoot: scriptRoot,
      projectVersion: readViewVersion(viewDir),
      projectDebug: protectSecrets
        ? '未收集：项目带密码输入框，框架与 agent 自己写的日志里可能有密码原文'
        : '已收集（顶层 maafw*.log 即 history 里各次的 .maafw.log，不重复收）',
      runs: selectedRuns.map(selected => ({
        history: `${selected.run.date}/${selected.run.user}/${selected.run.stamp}`,
        result: selected.result ?? null,
        success: selected.success,
        matchedBy: selected.matchedBy,
        frameworkLogs: frameworkLogsShareable.get(selected)
          ? '已收集'
          : '未收集：更早版本写的副本，可能有密码原文',
      })),
    })
  }

  await addMasDebugLogs(state, dataRoots)
  for (const { viewDir, archiveRoot } of projectDebugDirs) {
    await addProjectDebugDirectory(state, viewDir, archiveRoot)
  }
  deferred.sort(
    (left, right) =>
      Number(left.selected.success) - Number(right.selected.success) ||
      runOrderKey(right.selected).localeCompare(runOrderKey(left.selected))
  )
  for (const { scriptRoot, selected, includeNativeLog } of deferred) {
    await addRunHeavyFiles(state, scriptRoot, selected, includeNativeLog)
  }

  addReportManifest(state, 'manifest.json', {
    report: label,
    exportedAt: new Date().toISOString(),
    scripts: manifestScripts,
  })

  const collectedCount = state.entries.filter(entry => entry.status !== 'skipped').length
  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    await zip.writeZipPromise(zipPath)
    logger.info(`${label} 问题包已导出: ${zipPath}`)
    return {
      success: true,
      message: `${label} 问题包导出成功，已收集 ${collectedCount} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`${label} 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

/** 单个 MFW 脚本（含各特调）的问题包。 */
export async function createMaaFWIssueReport(
  appRoot: string,
  zipPath: string,
  scriptId: string
): Promise<IssueReportResult> {
  const script = findMaaFWScript(appRoot, scriptId)
  if (!script) {
    return { success: false, error: '没有找到这个 MFW 脚本，可能已被删除' }
  }
  return createIssueReport(appRoot, zipPath, [script], 'MFW')
}

/** 全部 M9A 脚本的问题包。 */
export async function createM9AIssueReport(
  appRoot: string,
  zipPath: string
): Promise<IssueReportResult> {
  const scripts = discoverMaaFWScripts(
    resolveDataRoots(appRoot),
    (_uid, type) => type === M9A_CONFIG_TYPE
  )
  return createIssueReport(appRoot, zipPath, scripts, 'M9A')
}
