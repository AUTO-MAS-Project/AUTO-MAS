/**
 * Runtime 初始化链路
 *
 * 灰度开关打开后，首次初始化的「装 Python → 装 pip → 装 Git → clone 仓库 → pip 装依赖」
 * 五步链换成一次 `auto-mas-runtime.exe bootstrap --version <目标版本>`：Runtime 内部按
 * uv → 仓库 → Python → 依赖的顺序完成全部准备工作，Electron 只负责把它的 stage 映射回
 * 现有初始化界面的 7 段模型，再另行启动后端（`backend supervise` 由 backendService 负责）。
 *
 * 本模块只做映射与编排，不改动旧链路的任何一行；旧链路仍由 initializationService 直接调用
 * environmentService / repositoryService / dependencyService。
 */

import { app } from 'electron'

import { getLogger } from './logger'
import { MirrorConfig, MirrorService } from './mirrorService'
import {
  CreateRuntimeClientOptions,
  RUNTIME_CLIENT_ERROR_DEFINITIONS,
  RuntimeClient,
  RuntimeMirrorSelection,
  RuntimeRemediation,
  RuntimeRunControl,
  RuntimeRunResult,
  RuntimeStage,
  RuntimeSupervisedLaunchConfig,
  createRuntimeClient,
  formatStartupLogs,
  isRuntimeClientError,
} from './runtime'

const logger = getLogger('Runtime初始化')

// ==================== 阶段模型 ====================

/** 现有初始化界面的 7 段模型，新链路必须映射成它才能被界面直接消费。 */
export type InitializationStage =
  | 'mirror'
  | 'python'
  | 'pip'
  | 'git'
  | 'repository'
  | 'dependency'
  | 'backend'
  | 'complete'

/**
 * 段状态。旧链路只发进度百分比，新链路额外给出机器可读的段状态，
 * 界面（W9d）据此判断段的开始与结束，不解析中文文案。
 */
export type InitializationStageStatus = 'started' | 'running' | 'completed' | 'failed'

/** 真正执行的段，不含只表示整条流程结束的 `complete`。 */
export type InitializationRunStage = Exclude<InitializationStage, 'complete'>

/** 段在现有界面里的固定序号（`complete` 由调用方按 totalStages 填）。 */
export const INITIALIZATION_STAGE_INDEX: Readonly<Record<InitializationRunStage, number>> = {
  mirror: 1,
  python: 2,
  pip: 3,
  git: 4,
  repository: 5,
  dependency: 6,
  backend: 7,
}

/**
 * Runtime stage 前缀到界面段的显式对应。
 *
 * `uv.*` 与 `python.*` 都落在 `python` 段：新链路里 uv 是 Python 环境的一部分，界面上
 * 没有单独的「uv」步骤。`backend.*` 只可能出现在 `backend supervise` 里，列在这里是为了
 * 让映射函数对全量 stage 都有确定结果。
 */
const RUNTIME_STAGE_PREFIX_MAP: readonly (readonly [string, InitializationRunStage])[] = [
  ['uv.', 'python'],
  ['python.', 'python'],
  ['workspace.', 'repository'],
  ['dependencies.', 'dependency'],
  ['backend.', 'backend'],
]

/**
 * 没有显式对应时落到的通用段。
 *
 * `bootstrap` / `repair` / `doctor` 这类顶层 stage 与协议后续新增的 stage 都走这里：
 * 协议要求调用方对未知 stage 使用通用展示而不是拒绝整个协议，所以这里绝不抛错。
 */
export const FALLBACK_INITIALIZATION_STAGE: InitializationRunStage = 'python'

/** 查显式对应；没有对应物时返回 null，供调用方区分「映射到了」与「兜底」。 */
export function mapRuntimeStageToInitializationStage(
  stage: RuntimeStage
): InitializationRunStage | null {
  for (const [prefix, mapped] of RUNTIME_STAGE_PREFIX_MAP) {
    if (stage.startsWith(prefix)) return mapped
  }
  return null
}

/** 把 Runtime stage 映射成界面段，未知 stage 落到通用段。 */
export function mapRuntimeStage(stage: RuntimeStage): InitializationRunStage {
  return mapRuntimeStageToInitializationStage(stage) ?? FALLBACK_INITIALIZATION_STAGE
}

// ==================== 镜像源映射 ====================

/**
 * 旧链路镜像键到 Runtime `--mirror <类型>=<键>` 的显式映射。
 *
 * 两套键名不是一套东西，逐项对照 Runtime 的 `internal/mirror/defaults.go` 后只有下面
 * 几项语义对得上，映射不到的一律不传 `--mirror`，交给 Runtime 自己按内置目录轮换：
 * - 旧 `python` 类是 python.org 的分发源，Runtime 的 `python` 类只有 GitHub 上的
 *   python-build-standalone，只有「官方」这一项对得上；
 * - 旧 `repo` 类的 gitee / gh-proxy 各变体 / ghfast 在 Runtime 的 `git` 类里没有对应源；
 * - 旧 `git` 类是「去哪下 git.exe」，Runtime 内置 Go Git 不再安装 Git，没有对应物；
 * - 旧 `pip_mirror` 类对应 Runtime 的 `package-index`。T13.4 之前 Runtime 在
 *   `bootstrap` / `dependencies *` / `repair` 上显式指定 `--mirror package-index=<键>`
 *   一律返回 INVALID_ARGUMENT；T13.4 起改为允许显式指定（改写的是锁文件里的索引副本，
 *   不覆盖 `uv.lock` 冻结的 registry URL），依赖段因此也能换镜像了——但只映射键名字面
 *   相同的三项（aliyun / tsinghua / ustc）。旧 `official` 对应 Runtime 的 `pypi`，键名
 *   对不上，不假定两边是同一个源，仍然不映射。
 */
const MIRROR_KEY_MAP: Readonly<
  Partial<Record<InitializationRunStage, Readonly<Record<string, RuntimeMirrorSelection>>>>
> = {
  python: {
    official: { kind: 'python', key: 'github' },
  },
  repository: {
    cnb: { kind: 'git', key: 'cnb' },
    github: { kind: 'git', key: 'github' },
  },
  dependency: {
    aliyun: { kind: 'package-index', key: 'aliyun' },
    tsinghua: { kind: 'package-index', key: 'tsinghua' },
    ustc: { kind: 'package-index', key: 'ustc' },
  },
}

/** 可供解析旧镜像选中值的最小依赖形状；`MirrorService` 结构上天然满足它。 */
export type MirrorLookup = Pick<MirrorService, 'getMirrors'>

/**
 * `MIRROR_KEY_MAP` 的段与旧链路镜像类型（`mirrorService.ts` 的 `MirrorConfig` 键）的对应。
 *
 * 只列 `RUNTIME_BOOTSTRAP_STAGE_ORDER` 里真正会传镜像选择的三段；`mirror` / `pip` / `git`
 * 在新链路没有对应物，`retryStage` 里直接短路，走不到这张表。
 */
const LEGACY_MIRROR_TYPE_BY_STAGE: Readonly<
  Partial<Record<InitializationRunStage, keyof MirrorConfig>>
> = {
  python: 'python',
  repository: 'repo',
  dependency: 'pip_mirror',
}

/**
 * 把界面选中的旧镜像标识解析成 `MirrorSource.key`。
 *
 * 旧链路的 `MirrorRotationService.execute(..., preferredMirrorName)` 按 `mirror.name`
 * 匹配，渲染进程存的选中值也是 `name`（`Initialization/index.vue` 的 `convertMirror`
 * 甚至把展示层的 `key` 字段本身都填成了 `name`）；但 `MIRROR_KEY_MAP` 是按
 * `MirrorSource.key` 建的表。两种取值都可能传进来，按 key 或 name 任一命中即可。
 */
function resolveMirrorSourceKey(
  mirrorService: MirrorLookup,
  stage: InitializationRunStage,
  selected: string
): string | null {
  const legacyType = LEGACY_MIRROR_TYPE_BY_STAGE[stage]
  if (!legacyType) return null
  const source = mirrorService
    .getMirrors(legacyType)
    .find(m => m.key === selected || m.name === selected)
  return source?.key ?? null
}

/**
 * 把界面上选中的旧镜像标识（`MirrorSource.key` 或 `name`）转成 Runtime 的镜像选择；
 * 解析不到旧镜像源、或解析到了但映射表没有对应项时都返回 null。
 */
export function mapMirrorSelection(
  mirrorService: MirrorLookup,
  stage: InitializationRunStage,
  selected: string | undefined
): RuntimeMirrorSelection | null {
  const trimmed = selected?.trim()
  if (!trimmed) return null
  const key = resolveMirrorSourceKey(mirrorService, stage, trimmed)
  if (!key) return null
  return MIRROR_KEY_MAP[stage]?.[key] ?? null
}

/**
 * 各段在 Runtime 链路下映射得到的旧镜像键，供界面过滤「换镜像重试」的候选列表。
 *
 * 界面不该把 Runtime 根本收不下的镜像源摆出来（选了也只会被忽略），也不该自己抄一份
 * 键名，所以这里把上面那张映射表的键原样导出，映射表是唯一真相源。列表为空的段
 * （`dependency` 等）在 Runtime 模式下不展示镜像选择。
 */
export function listRuntimeMappableMirrorKeys(): Record<InitializationRunStage, string[]> {
  const result = {} as Record<InitializationRunStage, string[]>
  for (const stage of Object.keys(INITIALIZATION_STAGE_INDEX) as InitializationRunStage[]) {
    result[stage] = Object.keys(MIRROR_KEY_MAP[stage] ?? {})
  }
  return result
}

// ==================== 目标版本 ====================

/**
 * 补齐 Runtime 要求的 `v` 前缀。
 *
 * Runtime 用目标版本拼 `release/<版本>` 分支名，版本号必须以 `v` 开头；
 * Electron 的 `app.getVersion()` 给的是不带 `v` 的 `5.5.0-beta.3`。
 */
export function toRuntimeVersion(raw: string): string {
  const trimmed = raw.trim()
  return trimmed.startsWith('v') ? trimmed : `v${trimmed}`
}

/** 首次安装的目标版本就是应用自身版本；更新流程的目标版本由更新任务另行给出。 */
export function resolveRuntimeTargetVersion(): string {
  return toRuntimeVersion(app.getVersion())
}

// ==================== 进度桥接 ====================

export interface BootstrapProgressUpdate {
  stage: InitializationRunStage
  status: InitializationStageStatus
  progress: number
  message: string
  /** Runtime 没有可靠总量时为 true，界面改用持续活动进度而不是展示伪百分比。 */
  indeterminate?: boolean
}

/** bootstrap 实际经过的三个界面段，按现有界面的固定先后顺序排列。 */
export const RUNTIME_BOOTSTRAP_STAGE_ORDER: readonly InitializationRunStage[] = [
  'python',
  'repository',
  'dependency',
]

/** 新链路没有对应物、进入 bootstrap 时立刻置为完成的三段。 */
export const RUNTIME_TAKEOVER_STAGES: readonly InitializationRunStage[] = ['mirror', 'pip', 'git']

export const RUNTIME_TAKEOVER_MESSAGE = '由 Runtime 接管'
export const RUNTIME_DEVELOPMENT_SKIP_MESSAGE = '由 Runtime development 模式接管，跳过'

/** 兼容旧消费方的段起始值；indeterminate=true 时界面不得把它显示成精确百分比。 */
const STAGE_STARTED_PROGRESS = 10

/**
 * 把 Runtime 的 progress / state 事件桥接成现有 7 段进度。
 *
 * 只往前走，不回退：真实 bootstrap 的顺序是 uv → 仓库 → Python → 依赖（本仓库
 * `runtime/__fixtures__/bootstrap-success.ndjson` 是真机跑出来的），而 `uv.*` 与
 * `python.*` 都映射到 `python` 段，直接按事件重开段会让界面从「拉取源码」倒退回
 * 「安装 Python」。落后于当前段的事件仍会展示 Runtime 自己的文案，只是挂在当前段上。
 *
 * 进度百分比只用 Runtime 真给的 `percent`：没有可靠总量时用 `indeterminate` 明确告诉
 * 界面展示持续活动状态。`progress=10` 只为兼容仍要求数字的旧消费方，不再作为精确百分比
 * 呈现；这样既保留当前 IPC 形状，也不会让长耗时阶段看起来卡死在 10%。
 */
export class BootstrapProgressBridge {
  private index = -1
  private closed = false

  constructor(private readonly emit: (update: BootstrapProgressUpdate) => void) {}

  /** 当前所在的段；尚未收到任何可映射事件时为 null。 */
  get currentStage(): InitializationRunStage | null {
    return this.index < 0 ? null : RUNTIME_BOOTSTRAP_STAGE_ORDER[this.index]
  }

  /** 进入 bootstrap：三个没有对应物的段立刻各发一个完成。 */
  takeOver(): void {
    for (const stage of RUNTIME_TAKEOVER_STAGES) {
      this.emit({
        stage,
        status: 'completed',
        progress: 100,
        message: RUNTIME_TAKEOVER_MESSAGE,
        indeterminate: false,
      })
    }
  }

  /** 消费一条 Runtime 事件。 */
  observe(stage: RuntimeStage, message: string, percent?: number): void {
    if (this.closed) return

    const mapped = mapRuntimeStage(stage)
    const wanted = RUNTIME_BOOTSTRAP_STAGE_ORDER.indexOf(mapped)
    // 落后段（含兜底段与 backend.*）挂在当前段上；一条事件都还没来过时从第一段开始。
    const target = wanted > this.index ? wanted : Math.max(this.index, 0)

    if (target > this.index) {
      this.closeStagesBefore(target)
      this.index = target
      this.emit({
        stage: RUNTIME_BOOTSTRAP_STAGE_ORDER[target],
        status: 'started',
        progress: percent === undefined ? STAGE_STARTED_PROGRESS : clampPercent(percent),
        message,
        indeterminate: percent === undefined,
      })
      return
    }

    this.emit({
      stage: RUNTIME_BOOTSTRAP_STAGE_ORDER[target],
      status: 'running',
      progress: percent === undefined ? STAGE_STARTED_PROGRESS : clampPercent(percent),
      message,
      indeterminate: percent === undefined,
    })
  }

  /** bootstrap 成功：把还没关掉的段补成完成。 */
  finish(message: string): void {
    if (this.closed) return
    this.closeStagesBefore(RUNTIME_BOOTSTRAP_STAGE_ORDER.length, message)
    this.index = RUNTIME_BOOTSTRAP_STAGE_ORDER.length
    this.closed = true
  }

  /** bootstrap 失败：在失败段上打一个 failed，后续事件不再发。 */
  fail(stage: InitializationRunStage, message: string): void {
    if (this.closed) return
    this.closed = true
    this.emit({ stage, status: 'failed', progress: 0, message, indeterminate: false })
  }

  /**
   * 把 [当前段, target) 之间的段全部置为完成。
   *
   * 还没进过任何段时什么都不发：单步重试只会跑到某一段，不能顺手把它前面那些
   * 本次根本没执行的段也报成完成。
   */
  private closeStagesBefore(target: number, message = '完成'): void {
    if (this.index < 0) return
    for (let i = this.index; i < target; i += 1) {
      this.emit({
        stage: RUNTIME_BOOTSTRAP_STAGE_ORDER[i],
        status: 'completed',
        progress: 100,
        message,
        indeterminate: false,
      })
    }
  }
}

function clampPercent(percent: number): number {
  if (!Number.isFinite(percent)) return STAGE_STARTED_PROGRESS
  return Math.min(100, Math.max(0, Math.round(percent)))
}

// ==================== 结果 ====================

/** Runtime 链路的失败细节，与旧链路的失败形状叠加，界面（W9d）按需消费。 */
export interface RuntimeStageOutcome {
  success: boolean
  error?: string
  /** Runtime 的结构化结果码；旧链路不产生。 */
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
  /** `[stdout]…\n\n[stderr]…` 整块文本，与旧链路失败界面的展示格式一致。 */
  logs?: string
  /**
   * Runtime 按命令与日期轮转的日志文件路径（`result.details.logPath`），供界面
   * 「打开日志」使用；不是每条命令都写日志文件，所以可能没有。
   */
  logPath?: string
  /** 映射后的失败段名。 */
  failedStage?: InitializationRunStage
}

/**
 * 从事件 details 里读 Runtime 自己的轮转日志路径。
 *
 * `details` 是裸 `Record<string, unknown>`，Runtime 只在写了日志文件的命令上放 `logPath`，
 * 所以拿不到就返回 undefined，由界面退回自己的日志文件。
 */
export function readRuntimeLogPath(details: Record<string, unknown>): string | undefined {
  const logPath = details.logPath
  return typeof logPath === 'string' && logPath.length > 0 ? logPath : undefined
}

/** 可注入的客户端工厂，便于单元测试替换掉真实子进程。 */
export type RuntimeClientFactory = (options: CreateRuntimeClientOptions) => RuntimeClient

/**
 * 单步重试的处置强度。
 *
 * `auto` 按上一次失败给出的 remediation 决定，是初始化界面「重试」按钮的行为；
 * 更新流程要在界面上同时摆出「重试同步」与「重建环境」两个按钮，所以还能显式指定。
 */
export type RuntimeRetryMode = 'auto' | 'sync' | 'rebuild'

export interface RuntimeInitializationOptions {
  launchConfig: RuntimeSupervisedLaunchConfig
  /** 解析镜像选择要用到的旧 `MirrorService`；复用调用方已有的实例，这里不再新建。 */
  mirrorService: MirrorLookup
  createClient?: RuntimeClientFactory
  /**
   * 本实例的目标版本，省略时用应用自身版本。
   *
   * 首次安装装的就是应用自身版本；更新流程要装的是另一个版本，用同一个编排器但换目标，
   * `bootstrap` 与 `workspace sync` 的 `--version` 都跟着它走。
   */
  targetVersion?: string
}

// 走统一工厂而不是裸 new RuntimeClient：遥测开关（AUTO_MAS_TELEMETRY）由 createRuntimeClient
// 注入，这里不用再重复读一遍配置。
const defaultClientFactory: RuntimeClientFactory = options => createRuntimeClient(options)

/**
 * Runtime 初始化链路的编排入口。
 *
 * 只持有本次生命周期的启动配置与「上一次失败给出的处置动作」，进程与协议细节全部在
 * RuntimeClient 里，后端启动仍由 backendService 负责（W9c）。
 */
export class RuntimeInitializationService {
  private readonly createClient: RuntimeClientFactory
  private readonly mirrorService: MirrorLookup
  /** 各段上一次失败给出的 remediation，决定单步重试用普通重试还是重建环境。 */
  private readonly lastRemediation = new Map<InitializationRunStage, RuntimeRemediation[]>()
  /** 在途命令的控制入口，用于下发 stdin `cancel`；没有命令在跑时为 null。 */
  private activeControl: RuntimeRunControl | null = null

  constructor(private readonly options: RuntimeInitializationOptions) {
    this.createClient = options.createClient ?? defaultClientFactory
    this.mirrorService = options.mirrorService
  }

  get launchConfig(): RuntimeSupervisedLaunchConfig {
    return this.options.launchConfig
  }

  /** 本实例的目标版本；省略时退回应用自身版本。 */
  get targetVersion(): string {
    return this.options.targetVersion ?? resolveRuntimeTargetVersion()
  }

  /**
   * 向在途命令下发 stdin `cancel`；没有命令在跑时返回 false。
   *
   * 只是「请求」取消：Runtime 在提交点之后的迟到取消不会把已激活的现场伪装成取消，
   * 最终结局仍以它给出的 `result` 为准。
   */
  cancel(): boolean {
    const control = this.activeControl
    if (!control) return false
    control.cancel()
    logger.info('已向在途 Runtime 命令下发 cancel')
    return true
  }

  /**
   * 跑一次 `bootstrap --version <目标版本>`，把阶段映射进 `onProgress`。
   *
   * bootstrap 只做准备工作，不启动后端；成功后由调用方另行启动 `backend supervise`。
   */
  async bootstrap(
    onProgress: (update: BootstrapProgressUpdate) => void,
    mirror?: RuntimeMirrorSelection | null
  ): Promise<RuntimeStageOutcome> {
    const version = this.targetVersion
    const bridge = new BootstrapProgressBridge(onProgress)
    bridge.takeOver()

    const outcome = await this.execute(['bootstrap', '--version', version], mirror, bridge)
    if (outcome.success) {
      bridge.finish('运行环境准备完成')
    } else {
      bridge.fail(
        outcome.failedStage ?? FALLBACK_INITIALIZATION_STAGE,
        outcome.error ?? '初始化失败'
      )
    }
    return outcome
  }

  /**
   * 单步重试。
   *
   * - 用户选了镜像源：镜像是全局选项，只能整条 `bootstrap` 重跑（映射不到就不传
   *   `--mirror`，用 Runtime 自己的默认轮换）；
   * - 没选镜像源：走该段对应的下层命令，处置强度按 `mode` 决定。
   *
   * `mirror` / `pip` / `git` 三段在新链路没有对应物，直接按成功返回。
   *
   * `mode` 显式覆盖上一次失败留下的判断：初始化界面的「重建环境」按钮传 `rebuild`，
   * 普通「重试」按钮走默认的 `auto`，两个按钮才不会做同一件事。
   */
  async retryStage(
    stage: InitializationRunStage,
    onProgress: (update: BootstrapProgressUpdate) => void,
    mirrorKey?: string,
    mode: RuntimeRetryMode = 'auto'
  ): Promise<RuntimeStageOutcome> {
    if (stage === 'mirror' || stage === 'pip' || stage === 'git') {
      logger.info(`${stage} 段在 Runtime 链路没有对应物，直接跳过`)
      onProgress({
        stage,
        status: 'completed',
        progress: 100,
        message: RUNTIME_TAKEOVER_MESSAGE,
      })
      return { success: true }
    }

    if (mirrorKey?.trim()) {
      const mirror = mapMirrorSelection(this.mirrorService, stage, mirrorKey)
      if (!mirror) {
        logger.info(`镜像源 ${mirrorKey} 在 Runtime 目录里没有对应源，按默认轮换重跑 bootstrap`)
      }
      return this.bootstrap(onProgress, mirror)
    }

    const command = this.resolveRetryCommand(stage, mode)
    if (!command) {
      logger.warn(`未知的重试段 ${stage}，按整条 bootstrap 重跑`)
      return this.bootstrap(onProgress)
    }

    const bridge = new BootstrapProgressBridge(onProgress)
    const outcome = await this.execute(command, null, bridge)
    if (outcome.success) {
      onProgress({ stage, status: 'completed', progress: 100, message: '完成' })
    } else {
      bridge.fail(outcome.failedStage ?? stage, outcome.error ?? '重试失败')
    }
    return outcome
  }

  /**
   * 单步重试用的下层命令。
   *
   * `python` 段的下层命令是 `environment ensure`，它只准备并校验固定版本 uv；本段还覆盖
   * 由 bootstrap 内部完成的 `uv python install`，所以要重建环境时直接用整体 `repair`，
   * 而不是只重跑 uv 那半截。
   *
   * `sync` / `rebuild` 由调用方显式给出时以它为准（界面上「重试」与「重建环境」是两个
   * 按钮）；`auto` 沿用上一次失败的 remediation。更新流程要拿本次会话实际会跑的命令给
   * 界面看，所以这个方法是公开的。
   */
  resolveRetryCommand(
    stage: InitializationRunStage,
    mode: RuntimeRetryMode = 'auto'
  ): string[] | null {
    const needsRebuild =
      mode === 'auto'
        ? (this.lastRemediation.get(stage)?.includes('rebuild-environment') ?? false)
        : mode === 'rebuild'

    switch (stage) {
      case 'python':
        return needsRebuild ? ['repair'] : ['environment', 'ensure']
      case 'repository':
        return ['workspace', 'sync', '--version', this.targetVersion]
      case 'dependency':
        return needsRebuild ? ['dependencies', 'rebuild'] : ['dependencies', 'sync']
      default:
        return null
    }
  }

  /**
   * 问 Runtime `doctor` 要一份受管布局体检结果。
   *
   * 返回 undefined 表示 doctor 自己没跑成，调用方按「查不出来」处理。
   */
  async doctor(): Promise<RuntimeDoctorCheck[] | undefined> {
    const runtimePath = this.options.launchConfig.runtimePath
    if (!runtimePath) return undefined

    try {
      const client = this.createClient({
        runtimePath,
        appRoot: this.options.launchConfig.appRoot,
        dataRoot: this.options.launchConfig.dataRoot,
        launchMode: this.options.launchConfig.mode,
      })
      const outcome = await client.run(['doctor'])
      if (!outcome.success) {
        logger.warn(`Runtime doctor 报告失败: ${outcome.code} ${outcome.result.message}`)
        return undefined
      }
      return parseDoctorChecks(outcome.result.details)
    } catch (error) {
      logger.warn(
        `Runtime doctor 调用失败: ${error instanceof Error ? error.message : String(error)}`
      )
      return undefined
    }
  }

  /** 跑一条 Runtime 命令，把事件桥接进进度，把失败转成现有失败形状。 */
  private async execute(
    command: string[],
    mirror: RuntimeMirrorSelection | null | undefined,
    bridge: BootstrapProgressBridge
  ): Promise<RuntimeStageOutcome> {
    const runtimePath = this.options.launchConfig.runtimePath
    if (!runtimePath) {
      // 灰度期一次生命周期只走一条链路，找不到可执行文件时直接失败展示，不回退旧链路。
      const definition = RUNTIME_CLIENT_ERROR_DEFINITIONS.RUNTIME_NOT_FOUND
      const message = `找不到 Runtime 可执行文件，无法以 ${this.options.launchConfig.mode} 模式初始化`
      logger.error(message)
      return {
        success: false,
        error: message,
        code: definition.code,
        retryable: definition.retryable,
        remediation: [...definition.remediation],
      }
    }

    // Runtime 把 uv / git 的原始输出逐行包成 log 事件转发，按流分开累积，
    // 失败时组装成现有失败界面直接展示的整块文本。
    const stdoutLines: string[] = []
    const stderrLines: string[] = []

    const client = this.createClient({
      runtimePath,
      appRoot: this.options.launchConfig.appRoot,
      dataRoot: this.options.launchConfig.dataRoot,
      launchMode: this.options.launchConfig.mode,
      mirrors: mirror ? [mirror] : undefined,
    })

    logger.info(
      `执行 Runtime 命令: ${command.join(' ')}${mirror ? `（镜像 ${mirror.kind}=${mirror.key}）` : ''}`
    )

    let outcome: RuntimeRunResult
    try {
      outcome = await client.run(command, {
        onStarted: control => {
          this.activeControl = control
        },
        onProgress: event => bridge.observe(event.stage, event.message, event.percent),
        onState: event => bridge.observe(event.stage, event.message),
        onLog: event => {
          if (event.stream === 'stderr') {
            stderrLines.push(event.message)
            return
          }
          stdoutLines.push(event.message)
        },
      })
    } catch (error) {
      if (isRuntimeClientError(error)) {
        logger.error(`Runtime 调用失败: ${error.code} ${error.message}`)
        return {
          success: false,
          error: error.message,
          code: error.code,
          retryable: error.retryable,
          remediation: [...error.remediation],
          logs: mergeRuntimeLogs(stdoutLines, stderrLines, error.details.stderr),
          failedStage: bridge.currentStage ?? FALLBACK_INITIALIZATION_STAGE,
        }
      }
      const message = error instanceof Error ? error.message : String(error)
      logger.error(`Runtime 调用失败: ${message}`)
      return {
        success: false,
        error: message,
        logs: mergeRuntimeLogs(stdoutLines, stderrLines),
        failedStage: bridge.currentStage ?? FALLBACK_INITIALIZATION_STAGE,
      }
    } finally {
      this.activeControl = null
    }

    if (outcome.success) {
      logger.info(`Runtime 命令完成: ${command.join(' ')}`)
      return { success: true }
    }

    // 失败段优先取主错误事件的 stage：result 上带的可能是 `bootstrap` 这种顶层 stage。
    const errorEvent = outcome.errors[outcome.errors.length - 1]
    const runtimeStage = errorEvent?.stage ?? outcome.result.stage
    const failedStage =
      mapRuntimeStageToInitializationStage(runtimeStage) ??
      bridge.currentStage ??
      FALLBACK_INITIALIZATION_STAGE
    const remediation = [...outcome.result.remediation]
    this.lastRemediation.set(failedStage, remediation)

    const message = outcome.result.message || `Runtime 命令失败（${outcome.code}）`
    logger.error(`Runtime 命令失败: ${outcome.code} ${message}`)
    return {
      success: false,
      error: message,
      code: outcome.code,
      retryable: outcome.result.retryable,
      remediation,
      logs: mergeRuntimeLogs(stdoutLines, stderrLines, outcome.stderr),
      logPath: readRuntimeLogPath(outcome.result.details),
      failedStage,
    }
  }
}

/** Runtime 自身的 stderr 诊断并入 `[stderr]` 块，避免失败界面一片空白。 */
function mergeRuntimeLogs(
  stdoutLines: string[],
  stderrLines: string[],
  runtimeStderr?: string
): string | undefined {
  const diagnostics = runtimeStderr?.trimEnd()
  const merged = diagnostics ? [...stderrLines, ...diagnostics.split(/\r?\n/)] : stderrLines
  return formatStartupLogs(stdoutLines, merged)
}

// ==================== doctor ====================

/** `doctor` 结果里的单项检查（result.details.checks）。 */
export interface RuntimeDoctorCheck {
  id: string
  name: string
  message: string
  /** 实测取值为 `ok` / `missing` / `error`。 */
  status: string
  details: Record<string, unknown>
}

function parseDoctorChecks(details: Record<string, unknown>): RuntimeDoctorCheck[] | undefined {
  const checks = details.checks
  if (!Array.isArray(checks)) return undefined

  const parsed: RuntimeDoctorCheck[] = []
  for (const raw of checks) {
    if (typeof raw !== 'object' || raw === null) continue
    const entry = raw as Record<string, unknown>
    if (typeof entry.id !== 'string' || typeof entry.status !== 'string') continue
    parsed.push({
      id: entry.id,
      name: typeof entry.name === 'string' ? entry.name : entry.id,
      message: typeof entry.message === 'string' ? entry.message : '',
      status: entry.status,
      details:
        typeof entry.details === 'object' && entry.details !== null
          ? (entry.details as Record<string, unknown>)
          : {},
    })
  }
  return parsed
}

/** 旧 `check-critical-files` 的返回形状。 */
export interface CriticalFilesCheck {
  pythonExists: boolean
  pipExists: boolean
  gitExists: boolean
  mainPyExists: boolean
  /**
   * doctor 的逐项检查原文，只有 Runtime 链路产生。
   *
   * 四个布尔量只回答「要不要初始化」，界面的「运行诊断」要展示的是每一项到底怎么了，
   * 所以原样带上而不是再压缩一次。
   */
  runtimeChecks?: RuntimeDoctorCheck[]
}

/**
 * 把 doctor 的检查项映射成旧的四个布尔量。
 *
 * 这四个布尔量存在的唯一目的是回答「要不要初始化」，新链路里权威答案只有一个：
 * `layout.repo` 缺失就是没装过。另外两项在新链路里没有对应物——不再单独装 pip（uv 管依赖），
 * 也不再安装 Git（Runtime 内置 Go Git）——恒为 true，不参与判定。
 */
export function mapDoctorChecksToCriticalFiles(checks: RuntimeDoctorCheck[]): CriticalFilesCheck {
  const byId = new Map(checks.map(check => [check.id, check]))
  const layoutRepo = byId.get('layout')?.details?.repo
  const repoPresent = layoutRepo !== undefined ? layoutRepo !== 'missing' : false

  return {
    pythonExists: byId.get('python')?.status === 'ok',
    pipExists: true,
    gitExists: true,
    mainPyExists: repoPresent,
    runtimeChecks: checks,
  }
}

// ==================== development 模式 ====================

/**
 * development 模式跳过全部安装步骤。
 *
 * 开发检出自带 `.venv`，Runtime 的 development 模式只监督这份源码，不创建也不更新它，
 * 所以六个准备段各发一个完成，直接进后端段。
 */
export function emitDevelopmentSkipProgress(
  onProgress: (update: BootstrapProgressUpdate) => void
): void {
  const stages: InitializationRunStage[] = [
    'mirror',
    'python',
    'pip',
    'git',
    'repository',
    'dependency',
  ]
  for (const stage of stages) {
    onProgress({
      stage,
      status: 'completed',
      progress: 100,
      message: RUNTIME_DEVELOPMENT_SKIP_MESSAGE,
      indeterminate: false,
    })
  }
}
