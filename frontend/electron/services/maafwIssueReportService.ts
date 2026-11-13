import { historyFilePath, readHistoryRecords, type HistoryRecordRow } from './historyReader'
import { readBackendDocument } from './backendConfig'
import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { parse as parseJson5 } from 'json5'

import { getLogger } from './logger'
import { probeProjectRuntime } from './maafwProjectRuntimeProbe'
import {
  CollectorState,
  addDebugDirectory,
  addDiagnosticFile,
  addReportHistoryLog,
  addReportHistoryJson,
  addDirectory,
  addReportManifest,
  addSanitizedJsonFile,
  addSanitizedJsonValue,
  addVerbatimTextFile,
  isRecord,
  readJson,
  readReportHistory,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('MFW问题包')

// 与 app/models/config.py 的 M9AConfig / MSSConfig 类名同步
const M9A_CONFIG_TYPE = 'M9AConfig'
const MSS_CONFIG_TYPE = 'MSSConfig'
// 一键导出 M9A / MSS 时一个现存脚本都没有（或都读不到 interface），按这两个项目 interface 的
// name 认已删脚本的运行（m9a 的 label 是 M9A，比较时一律小写）
const M9A_PROJECT_NAME = 'm9a'
const MSS_PROJECT_NAME = 'maastarresonance'

// 与 app/task/MaaFW/tools/embedded/embedded_project.py 的 embedded_copy_dir_name 同步：
// 每个脚本的项目视图是 data/mfw/<脚本 uuid 去掉连字符的前 12 位>/
const VIEW_DIR_NAME_LENGTH = 12

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

// 与 app/task/MaaFW/tools/embedded/runner_task.py 的 _format_run_overview_log 同步：每次运行的主日志
// 里有一行「MaaFW 运行总览: project=<名字>; ...」，<名字> 取 interface 的 label（空或 $ 开头时取
// name）。脚本删掉后视图跟着删，靠这一行认出已删脚本的运行属于哪个项目；worker 没跑到生成计划
// 就失败的运行没有这一行，认不出来
const RUN_OVERVIEW_PROJECT_PATTERN = /MaaFW 运行总览: project=([^;\r\n]+);/
const MAIN_LOG_HEAD_BYTES = 256 * 1024

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

interface MaaFWScript {
  uid: string
  /** ScriptConfig.json 里的配置类名，如 'MaaFWConfig' / 'M9AConfig' */
  type: string
  name: string
  projectLabel: string
  dataRoot: string
  viewDirName: string
  config: Record<string, unknown>
  userNames: string[]
}

/** 设置页下拉的一项：同一个项目（interface 的 name）的脚本合成一组。 */
export interface MaaFWIssueReportProject {
  /** 组键：interface 的 name 去空白转小写；读不到 interface 时是脚本的配置类名 */
  key: string
  label: string
  scriptCount: number
  /** 现存脚本里已经没有、只在最近的运行历史里出现的项目 */
  deletedOnly: boolean
  /** 组里现存脚本的配置类名 */
  types: string[]
}

interface ProjectGroup {
  key: string
  label: string
  scripts: MaaFWScript[]
  /** 认运行用：组里各脚本 interface 的 name 与 label（小写） */
  names: Set<string>
}

/** 一个数据根下认已删脚本运行要用的东西。 */
interface DataRootRuns {
  runs: HistoryRun[]
  /** 该数据根下全部现存脚本（不限类型） */
  scripts: MaaFWScript[]
  sourceKeys: Array<{ uid: string; key: string }>
}

interface HistoryRun {
  date: string
  user: string
  stamp: string
  record: HistoryRecordRow
  dataRoot: string
  log?: string
  workerLog?: string
  maafwLog?: string
  /** 项目 agent 自己写的日志本次新增的部分（debug/custom、go-service …），写的时候已打码 */
  projectLog?: string
  screenshots: string[]
  /** .worker.log 里认出的项目视图；null 表示读过但没认出来 */
  viewDirName?: string | null
  /** 主日志运行总览里的项目名；null 表示读过但没有这一行 */
  projectName?: string | null
}

interface SelectedRun {
  run: HistoryRun
  result?: string
  success: boolean
  matchedBy: 'projectPath' | 'userName' | 'projectName'
}

interface IssueReportResult {
  success: boolean
  incompleteCount?: number
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
    // 列项目时要把 30 天内每次运行的主日志开头都读一遍，按文件实际大小分配，不每次都开满
    const length = Math.min(bytes, fs.fstatSync(fd).size)
    const buffer = Buffer.alloc(length)
    const read = fs.readSync(fd, buffer, 0, length, 0)
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
  const userData = config.UserData
  if (!isRecord(userData) || !Array.isArray(userData.order)) {
    return []
  }

  const names = new Set<string>()
  for (const instance of userData.order) {
    const uid = isRecord(instance) && typeof instance.uid === 'string' ? instance.uid : ''
    const user = uid && isRecord(userData.data) ? userData.data[uid] : undefined
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
    const scriptConfig = readBackendDocument(dataRoot, 'scripts.yaml', 'ScriptConfig.json')
    if (!isRecord(scriptConfig) || !Array.isArray(scriptConfig.order)) {
      continue
    }

    for (const instance of scriptConfig.order) {
      if (!isRecord(instance)) {
        continue
      }
      const uid = typeof instance.uid === 'string' ? instance.uid : ''
      const type = typeof instance.type === 'string' ? instance.type : ''
      const viewDirName = viewDirNameOf(uid)
      const config = isRecord(scriptConfig.data) ? scriptConfig.data[uid] : undefined
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

function viewDirOf(script: MaaFWScript): string {
  return path.join(script.dataRoot, 'data', 'mfw', script.viewDirName)
}

/** 视图里 interface.json 顶层的 name 与 label（$ 开头的 i18n 键不算）；读不到返回 undefined。 */
function readProjectIdentity(viewDir: string): { name: string; label: string } | undefined {
  let parsed: unknown
  try {
    // interface 允许 JSON5（注释、键名不带引号）
    parsed = parseJson5(
      fs.readFileSync(path.join(viewDir, 'interface.json'), 'utf-8').replace(/^﻿/, '')
    )
  } catch {
    return undefined
  }
  const name = stringField(parsed, 'name')
  if (!name) {
    return undefined
  }
  const label = stringField(parsed, 'label')
  return { name, label: label.startsWith('$') ? '' : label }
}

/** 按项目分组，组的顺序就是各组第一个脚本的顺序。 */
function groupScriptsByProject(scripts: MaaFWScript[]): Map<string, ProjectGroup> {
  const groups = new Map<string, ProjectGroup>()
  const nameLabels = new Map<ProjectGroup, string>()
  for (const script of scripts) {
    const identity = readProjectIdentity(viewDirOf(script))
    const key = identity ? identity.name.toLowerCase() : script.type
    let group = groups.get(key)
    if (!group) {
      group = { key, label: '', scripts: [], names: new Set() }
      groups.set(key, group)
    }
    group.scripts.push(script)
    if (identity) {
      group.names.add(identity.name.toLowerCase())
      if (identity.label) {
        group.names.add(identity.label.toLowerCase())
      }
      group.label ||= identity.label
      if (!nameLabels.has(group)) {
        nameLabels.set(group, identity.name)
      }
    }
  }
  // 显示名：组里有 label 用 label，没有用 interface 的 name，都读不到用脚本名
  for (const group of groups.values()) {
    group.label ||= nameLabels.get(group) ?? group.scripts[0].name
  }
  return groups
}

function historyRunsOf(dataRoot: string, records: HistoryRecordRow[]): HistoryRun[] {
  const dates = [...new Set(records.map(record => record.date))]
    .sort()
    .reverse()
    .slice(0, HISTORY_SCAN_DAYS)
  return records
    .filter(record => dates.includes(record.date))
    .map(record => {
      const byRole = (role: string) => {
        const attachment = record.attachments.find(item => item.role === role && item.available)
        return attachment ? historyFilePath(dataRoot, attachment.relative_path) : undefined
      }
      return {
        record,
        dataRoot,
        date: record.date,
        user: record.username,
        stamp: String(record.id),
        log: historyFilePath(dataRoot, record.log_path),
        workerLog: byRole('worker_log'),
        maafwLog: byRole('native_log'),
        projectLog: byRole('project_log'),
        screenshots: record.attachments
          .filter(item => item.kind === 'image' && item.available)
          .flatMap(item => historyFilePath(dataRoot, item.relative_path) ?? []),
      }
    })
}

function scanHistoryRuns(
  dataRoot: string,
  state: CollectorState,
  archiveRoot: string
): HistoryRun[] {
  return historyRunsOf(dataRoot, readReportHistory(state, dataRoot, archiveRoot))
}

/** 列项目用：没有问题包可写，历史读不了就当没有。 */
function listHistoryRuns(dataRoot: string): HistoryRun[] {
  try {
    return historyRunsOf(dataRoot, readHistoryRecords(dataRoot))
  } catch (error) {
    logger.warn(`读取运行历史失败: ${dataRoot}, ${String(error)}`)
    return []
  }
}

function runProjectName(run: HistoryRun): string | null {
  if (run.projectName === undefined) {
    const head = run.log ? readHead(run.log, MAIN_LOG_HEAD_BYTES) : ''
    run.projectName = RUN_OVERVIEW_PROJECT_PATTERN.exec(head)?.[1]?.trim() || null
  }
  return run.projectName
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

/** 同一数据根下所有脚本（不限类型）的导入来源，用来认没有视图路径的旧记录。 */
function sourcePathKeysOf(dataRoot: string): Array<{ uid: string; key: string }> {
  const scriptConfig = readBackendDocument(dataRoot, 'scripts.yaml', 'ScriptConfig.json')
  if (!isRecord(scriptConfig) || !Array.isArray(scriptConfig.order)) {
    return []
  }
  return scriptConfig.order.flatMap(instance => {
    const uid = isRecord(instance) && typeof instance.uid === 'string' ? instance.uid : ''
    const config = uid
      ? isRecord(scriptConfig.data)
        ? scriptConfig.data[uid]
        : undefined
      : undefined
    const key = isRecord(config) ? pathKey(stringField(config.Info, 'Path')) : ''
    return key ? [{ uid, key }] : []
  })
}

function claimRun(
  run: HistoryRun,
  script: MaaFWScript,
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

  // worker 未产生可识别路径时只按保存时的名称快照认领，不推断脚本执行结果。
  return run.record.script_name === script.name && script.userNames.includes(run.user)
    ? 'userName'
    : undefined
}

/** 最近 RECENT_RUN_COUNT 次运行，外加最近 RECENT_FAILED_RUN_COUNT 次失败，新的在前。 */
function selectRuns(
  runs: HistoryRun[],
  claim: (run: HistoryRun) => SelectedRun['matchedBy'] | undefined
): SelectedRun[] {
  const selected: SelectedRun[] = []
  let claimedCount = 0
  let failedCount = 0

  for (const run of runs) {
    if (claimedCount >= RECENT_RUN_COUNT && failedCount >= RECENT_FAILED_RUN_COUNT) {
      break
    }

    const result = run.record.message
    const matchedBy = claim(run)
    if (!matchedBy) {
      continue
    }

    const success = run.record.status === 'success'
    const failed = run.record.status === 'error'
    if (claimedCount < RECENT_RUN_COUNT || (failed && failedCount < RECENT_FAILED_RUN_COUNT)) {
      selected.push({ run, result, success, matchedBy })
    }
    claimedCount += 1
    if (failed) {
      failedCount += 1
    }
  }

  return selected
}

function dataRootRunsOf(dataRoot: string, runs: HistoryRun[]): DataRootRuns {
  return {
    runs,
    scripts: discoverMaaFWScripts([dataRoot], () => true),
    sourceKeys: sourcePathKeysOf(dataRoot),
  }
}

/**
 * 已删脚本的运行：没被任何现存脚本认领（认领已含视图 id 属于某个现存脚本的情况）。
 * 删脚本时后端连视图一起删，这些运行只能靠主日志里的项目名归组。
 */
function isDeletedScriptRun(run: HistoryRun, context: DataRootRuns): boolean {
  return !context.scripts.some(script => claimRun(run, script, context.sourceKeys))
}

function deletedScriptRunsOf(context: DataRootRuns, projectNames: Set<string>): HistoryRun[] {
  return context.runs.filter(run => {
    const project = runProjectName(run)
    return !!project && projectNames.has(project.toLowerCase()) && isDeletedScriptRun(run, context)
  })
}

function safeFileName(value: string): string {
  return value
    .replace(/[\\/:*?"<>|\s]+/g, '_')
    .replace(/^[._]+|[._]+$/g, '')
    .slice(0, 40)
}

interface DeletedOwner {
  /** 视图 id；.worker.log 里没有视图路径的旧运行用脚本名 */
  owner: string
  archiveRoot: string
  scriptNames: string[]
  selectedRuns: SelectedRun[]
}

/** 已删脚本的运行按所有者分开，每个所有者同样取最近几次加最近几次失败；最近跑过的在前。 */
function deletedOwnersOf(runs: HistoryRun[]): DeletedOwner[] {
  const byOwner = new Map<string, { owner: string; runs: HistoryRun[] }>()
  for (const run of runs) {
    const owner = workerLogViewDirName(run) ?? run.record.script_name
    const archiveRoot = `scripts/deleted-${safeFileName(owner) || 'unknown'}`
    const entry = byOwner.get(archiveRoot) ?? { owner, runs: [] }
    entry.runs.push(run)
    byOwner.set(archiveRoot, entry)
  }
  return [...byOwner.entries()]
    .map(([archiveRoot, { owner, runs: ownerRuns }]) => {
      // 可能来自几个数据根，合起来重新按时间排
      ownerRuns.sort(
        (left, right) =>
          right.record.timestamp - left.record.timestamp ||
          right.record.id.localeCompare(left.record.id)
      )
      return {
        owner,
        archiveRoot,
        scriptNames: [...new Set(ownerRuns.map(run => run.record.script_name))],
        selectedRuns: selectRuns(ownerRuns, () => 'projectName'),
      }
    })
    .sort(
      (left, right) =>
        right.selectedRuns[0].run.record.timestamp - left.selectedRuns[0].run.record.timestamp
    )
}

/** 设置页下拉用：按项目列出指定配置类的脚本（配置类名由前端特调注册表给出），外加只剩历史的项目。 */
export function listMaaFWIssueReportProjects(
  appRoot: string,
  configTypes: string[]
): MaaFWIssueReportProject[] {
  const accepted = new Set(configTypes)
  const dataRoots = resolveDataRoots(appRoot)
  const groups = groupScriptsByProject(
    discoverMaaFWScripts(dataRoots, (_uid, type) => accepted.has(type))
  )
  const knownNames = new Set([...groups.values()].flatMap(group => [...group.names]))

  // 只剩历史的项目：显示名取最近一次运行里的原值
  const historyOnly = new Map<string, string>()
  for (const dataRoot of dataRoots) {
    const context = dataRootRunsOf(dataRoot, listHistoryRuns(dataRoot))
    for (const run of context.runs) {
      const project = runProjectName(run)
      const key = project?.toLowerCase()
      if (!project || !key || knownNames.has(key) || historyOnly.has(key)) {
        continue
      }
      if (isDeletedScriptRun(run, context)) {
        historyOnly.set(key, project)
      }
    }
  }

  return [
    ...[...groups.values()].map(group => ({
      key: group.key,
      label: group.label,
      scriptCount: group.scripts.length,
      deletedOnly: false,
      types: [...new Set(group.scripts.map(script => script.type))],
    })),
    ...[...historyOnly.entries()].map(([key, label]) => ({
      key,
      label,
      scriptCount: 0,
      deletedOnly: true,
      types: [],
    })),
  ]
}

/** 按组键找组：先看现存脚本，没有就当只剩历史的项目，在历史里找它的原名。 */
function findProjectGroup(appRoot: string, projectKey: string): ProjectGroup | undefined {
  const dataRoots = resolveDataRoots(appRoot)
  const group = groupScriptsByProject(discoverMaaFWScripts(dataRoots, () => true)).get(projectKey)
  if (group) {
    return group
  }
  for (const dataRoot of dataRoots) {
    for (const run of listHistoryRuns(dataRoot)) {
      const project = runProjectName(run)
      if (project && project.toLowerCase() === projectKey) {
        return { key: projectKey, label: project, scripts: [], names: new Set([projectKey]) }
      }
    }
  }
  return undefined
}

/** 问题包默认文件名前缀：带上项目名，一眼能看出是哪个项目的包。 */
export function maafwIssueReportFileNamePrefix(appRoot: string, projectKey: string): string {
  const safeName = safeFileName(findProjectGroup(appRoot, projectKey)?.label ?? '')
  return safeName ? `MFW-${safeName}-logs` : 'MFW-logs'
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
        if (!importPath) {
          continue
        }
        // 后端加载器对每一层 import 都相对 interface 根目录解析；相对当前文件所在目录的也看一眼，
        // 两处有一个存在就算（读不到的会被跳过）
        for (const target of new Set([
          path.resolve(viewDir, importPath),
          path.resolve(path.dirname(filePath), importPath),
        ])) {
          if (isInside(viewDir, target)) {
            pending.push(target)
          }
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

// {option: 值}，input 类型 option 的值是 {字段: 值}。旧版本存下的密码是明文（下次保存才加密），
// 项目有 password 输入框时 input 的值一律打码。用户快照里有两处：taskOptions 是
// {任务实例: {option: 值}}，globalOptions（全局选项，每个用户一份）就是 {option: 值}
function maskInputOptionMap(options: unknown): unknown {
  if (!isRecord(options)) {
    return options
  }
  return Object.fromEntries(
    Object.entries(options).map(([name, item]) => [
      name,
      isRecord(item) ? maskStringLeaves(item) : item,
    ])
  )
}

function maskInputOptionValues(taskOptions: unknown): unknown {
  if (!isRecord(taskOptions)) {
    return taskOptions
  }
  return Object.fromEntries(
    Object.entries(taskOptions).map(([task, options]) => [task, maskInputOptionMap(options)])
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
        if (!maskInputOptions) {
          return [key, redacted]
        }
        if (key === 'taskOptions') {
          return [key, maskInputOptionValues(redacted)]
        }
        return [key, key === 'globalOptions' ? maskInputOptionMap(redacted) : redacted]
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
  return path.posix.join(scriptRoot, 'history', run.date, run.stamp, path.basename(filePath))
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

/** 选中运行的文本日志；frameworkLogsShareable 为假的不收 .worker.log / .project.log。 */
function addRunTextFiles(
  state: CollectorState,
  scriptRoot: string,
  selectedRuns: SelectedRun[],
  frameworkLogsShareable: Map<SelectedRun, boolean>
): void {
  for (const selected of selectedRuns) {
    const { run } = selected
    const shareable = frameworkLogsShareable.get(selected)
    addReportHistoryJson(
      state,
      run.record,
      `${scriptRoot}/history/${run.date}/${run.stamp}/record.json`
    )
    if (!run.log) {
      const archivePath = `${scriptRoot}/history/${run.date}/${run.stamp}/main.log`
      addReportHistoryLog(state, run.dataRoot, run.record, archivePath)
    }
    const workerLog = shareable ? run.workerLog : undefined
    // .project.log 写的时候已按全部用户的密码打码，这里仍与 .worker.log 同一条件从严
    const projectLog = shareable ? run.projectLog : undefined
    for (const filePath of [run.log, workerLog, projectLog]) {
      if (filePath) {
        addDiagnosticFile(state, filePath, historyArchivePath(scriptRoot, run, filePath))
      }
    }
  }
}

function manifestRunsOf(
  selectedRuns: SelectedRun[],
  frameworkLogsShareable: Map<SelectedRun, boolean>
): Record<string, unknown>[] {
  return selectedRuns.map(selected => ({
    history: `${selected.run.date}/${selected.run.stamp}`,
    result: selected.result ?? null,
    success: selected.success,
    matchedBy: selected.matchedBy,
    frameworkLogs: frameworkLogsShareable.get(selected)
      ? '已收集'
      : '未收集：更早版本写的副本，可能有密码原文',
  }))
}

/**
 * 收集顺序就是问题包总大小受限时的取舍顺序（先收的先占额度，后面的被截断或跳过）：
 * 1. 各脚本的配置、项目版本与 interface、选中运行的文本日志（.json / .log / .worker.log）
 * 2. 各脚本最近一次失败（没有失败就是最近一次）运行的原生日志副本与失败截图
 * 3. 同项目已删脚本选中运行的文本日志
 * 4. MAS 自己的日志目录
 * 5. 项目自己的 debug 目录（agent、项目自定义日志等）
 * 6. 其余选中运行（含已删脚本的）的原生日志副本与失败截图：失败的在前，同类新的在前
 *
 * projectNames 是这一组项目的名字（小写），用来从各数据根的历史里认已删脚本的运行。
 */
async function createIssueReport(
  appRoot: string,
  zipPath: string,
  scripts: MaaFWScript[],
  projectNames: Set<string>,
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
  let anyProtectSecrets = false
  // 各脚本的运行时检查并行起跑（每个最多 15 秒），收集到它时再取结果
  const runtimeProbes = new Map(
    scripts.map(script => [
      script,
      probeProjectRuntime(path.join(script.dataRoot, 'data', 'mfw', script.viewDirName)),
    ])
  )

  for (const script of scripts) {
    const scriptRoot = `scripts/${script.viewDirName}`
    const viewDir = path.join(script.dataRoot, 'data', 'mfw', script.viewDirName)
    if (!runsByDataRoot.has(script.dataRoot)) {
      runsByDataRoot.set(
        script.dataRoot,
        scanHistoryRuns(script.dataRoot, state, `${scriptRoot}/history`)
      )
      sourceKeysByDataRoot.set(script.dataRoot, sourcePathKeysOf(script.dataRoot))
    }
    const sourceKeys = sourceKeysByDataRoot.get(script.dataRoot) ?? []
    const selectedRuns = selectRuns(runsByDataRoot.get(script.dataRoot) ?? [], run =>
      claimRun(run, script, sourceKeys)
    )
    // 项目有 password 输入框（或配置里已经有加密的密码值）时，日志里可能有密码原文，
    // 脚本配置里 input 选项的值也打码
    const protectSecrets =
      JSON.stringify(script.config).includes(SEALED_SECRET_PREFIX) ||
      projectDeclaresPasswordInput(viewDir)
    anyProtectSecrets ||= protectSecrets

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
    // interface.json 按原文收：resource[].path 这类相对路径正是排查「资源加载失败 / 投影漏文件」
    // 要看的，按键名脱敏会被整段换成 ***
    addVerbatimTextFile(
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

    addRunTextFiles(state, scriptRoot, selectedRuns, frameworkLogsShareable)

    const focusRun =
      selectedRuns.find(selected => selected.run.record.status === 'error') ?? selectedRuns[0]
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
      projectRuntime: await runtimeProbes.get(script),
      projectDebug: protectSecrets
        ? '未收集：项目带密码输入框，框架与 agent 自己写的日志里可能有密码原文'
        : '已收集（顶层 maafw*.log 即 history 里各次的 .maafw.log，不重复收）',
      runs: manifestRunsOf(selectedRuns, frameworkLogsShareable),
    })
  }

  // 同项目已删脚本的运行：视图已经跟着脚本删了，只有运行历史，没有配置和项目目录。
  // 密码从严：同组有现存脚本时随它们（任一要打码就打码），没有现存脚本时一律按要打码处理
  const protectDeletedSecrets = scripts.length === 0 || anyProtectSecrets
  const deletedRuns = dataRoots.flatMap(dataRoot => {
    if (!runsByDataRoot.has(dataRoot)) {
      runsByDataRoot.set(dataRoot, scanHistoryRuns(dataRoot, state, 'scripts/deleted/history'))
    }
    return deletedScriptRunsOf(
      dataRootRunsOf(dataRoot, runsByDataRoot.get(dataRoot) ?? []),
      projectNames
    )
  })
  for (const { owner, archiveRoot, scriptNames, selectedRuns } of deletedOwnersOf(deletedRuns)) {
    const frameworkLogsShareable = new Map(
      selectedRuns.map(selected => [
        selected,
        !protectDeletedSecrets || workerLogRedactedAtWrite(selected.run),
      ])
    )
    addRunTextFiles(state, archiveRoot, selectedRuns, frameworkLogsShareable)
    deferred.push(
      ...selectedRuns.map(selected => ({
        scriptRoot: archiveRoot,
        selected,
        includeNativeLog: !!frameworkLogsShareable.get(selected),
      }))
    )
    manifestScripts.push({
      deleted: true,
      owner,
      scriptNames,
      archiveRoot,
      runs: manifestRunsOf(selectedRuns, frameworkLogsShareable),
    })
  }

  await addMasDebugLogs(state, dataRoots)
  for (const { viewDir, archiveRoot } of projectDebugDirs) {
    await addProjectDebugDirectory(state, viewDir, archiveRoot)
  }
  deferred.sort(
    (left, right) =>
      Number(left.selected.success) - Number(right.selected.success) ||
      right.selected.run.record.timestamp - left.selected.run.record.timestamp ||
      right.selected.run.record.id.localeCompare(left.selected.run.record.id)
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
      incompleteCount: state.entries.filter(entry => entry.status !== 'included').length,
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

/** 一个 MFW 项目（含各特调）的问题包：该项目的现存脚本，加同项目已删脚本的运行。 */
export async function createMaaFWIssueReport(
  appRoot: string,
  zipPath: string,
  projectKey: string
): Promise<IssueReportResult> {
  const group = findProjectGroup(appRoot, projectKey)
  if (!group) {
    return { success: false, error: '没有找到这个 MFW 项目的脚本或运行记录' }
  }
  return createIssueReport(appRoot, zipPath, group.scripts, group.names, 'MFW')
}

/** 某个特调配置类全部现存脚本，加同项目已删脚本的运行。 */
async function createFlavorIssueReport(
  appRoot: string,
  zipPath: string,
  configType: string,
  fallbackProjectName: string,
  label: string
): Promise<IssueReportResult> {
  const scripts = discoverMaaFWScripts(
    resolveDataRoots(appRoot),
    (_uid, type) => type === configType
  )
  const projectNames = new Set(
    [...groupScriptsByProject(scripts).values()].flatMap(group => [...group.names])
  )
  if (projectNames.size === 0) {
    projectNames.add(fallbackProjectName)
  }
  return createIssueReport(appRoot, zipPath, scripts, projectNames, label)
}

/** 全部 M9A 脚本的问题包。 */
export async function createM9AIssueReport(
  appRoot: string,
  zipPath: string
): Promise<IssueReportResult> {
  return createFlavorIssueReport(appRoot, zipPath, M9A_CONFIG_TYPE, M9A_PROJECT_NAME, 'M9A')
}

/** 全部 MSS 脚本的问题包。 */
export async function createMSSIssueReport(
  appRoot: string,
  zipPath: string
): Promise<IssueReportResult> {
  return createFlavorIssueReport(appRoot, zipPath, MSS_CONFIG_TYPE, MSS_PROJECT_NAME, 'MSS')
}
