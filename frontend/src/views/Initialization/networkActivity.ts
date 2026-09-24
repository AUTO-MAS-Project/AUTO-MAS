/**
 * 初始化页「网络细节」的纯状态归并与格式化。
 *
 * Runtime（M14 起）在下载前会对各镜像源测速，下载时会报出当前文件、字节进度、速度与来源；
 * 这些都随进度事件一条条到达，页面需要把它们攒成两种可展示的形态：
 *
 * - 测速：按到达顺序累积每个源的实测结果，`succeeded` 时记下 Runtime 给的最终顺序文案；
 * - 传输：只保留最新一条带文件名的进度。
 *
 * 判定只看 `runtimeStage` / `runtimeStatus` 与几个数值字段，不解析 `message` 文案。
 * 旧版 Runtime 与旧链路的进度没有这些字段，状态始终为空，界面与以前一致。
 */

import { formatBytes, formatSpeed } from '@/utils/byteFormat'

/** 下载前测速的 Runtime stage。与 electron 侧 `NETWORK_PROBE_STAGE` 同值。 */
export const NETWORK_PROBE_STAGE = 'network.probe'

interface NetworkProbeEntry {
  source: string
  /**
   * 该源实测吞吐（字节/秒）。
   *
   * 三种取值三种含义：正数是实测吞吐；`0` 是探测失败；缺失（undefined）是探测成功但只测了
   * 首字节、没有吞吐可报（git 类源），仍然可用。
   */
  bytesPerSecond?: number
}

interface NetworkProbe {
  entries: NetworkProbeEntry[]
  /** 本轮测速结束后 Runtime 给出的最终顺序文案；还在测时为 null。 */
  summary: string | null
}

interface NetworkTransfer {
  /** 产生这条进度的 Runtime stage，用于判断后续无文件名的事件是否还属于同一次下载。 */
  stage: string
  item: string
  source?: string
  bytesPerSecond?: number
  current?: number
  total?: number
}

export interface NetworkActivity {
  probe: NetworkProbe | null
  transfer: NetworkTransfer | null
  /**
   * 本次运行里是否出现过任何网络细节。
   *
   * 出现过之后细节行的位置就一直留着（哪怕暂时为空），免得整块居中内容上下跳；
   * 一次都没出现过（旧版 Runtime、旧链路）则完全不占位，界面与以前一致。
   */
  seen: boolean
}

export const EMPTY_NETWORK_ACTIVITY: NetworkActivity = Object.freeze({
  probe: null,
  transfer: null,
  seen: false,
})

/** 进度载荷里与网络细节有关的字段，全部可选。 */
export interface NetworkActivityPayload {
  runtimeStage?: string
  runtimeStatus?: string
  message?: string
  item?: string
  source?: string
  bytesPerSecond?: number
  current?: number
  total?: number
}

function reduceProbe(state: NetworkActivity, payload: NetworkActivityPayload): NetworkActivity {
  // 上一轮已经收口（有 summary）后再来的事件属于新一轮：uv、git、python、package-index
  // 各测各的，列表不能把几轮混在一起。
  const ongoing = state.probe && state.probe.summary === null ? state.probe : null

  if (payload.runtimeStatus === 'running' && payload.source) {
    const entry: NetworkProbeEntry = {
      source: payload.source,
      bytesPerSecond: payload.bytesPerSecond,
    }
    const entries = ongoing ? [...ongoing.entries] : []
    const existing = entries.findIndex(item => item.source === entry.source)
    if (existing >= 0) {
      entries[existing] = entry
    } else {
      entries.push(entry)
    }
    return { probe: { entries, summary: null }, transfer: null, seen: true }
  }

  if (payload.runtimeStatus === 'succeeded') {
    return {
      probe: { entries: ongoing?.entries ?? [], summary: payload.message ?? '' },
      transfer: null,
      seen: true,
    }
  }

  return state
}

/**
 * 用一条进度载荷推进网络细节状态；无关的载荷原样返回同一个对象，方便调用方省掉一次赋值。
 */
export function reduceNetworkActivity(
  state: NetworkActivity,
  payload: NetworkActivityPayload
): NetworkActivity {
  if (payload.runtimeStage === NETWORK_PROBE_STAGE) {
    return reduceProbe(state, payload)
  }

  if (payload.item && payload.runtimeStage) {
    return {
      probe: null,
      transfer: {
        stage: payload.runtimeStage,
        item: payload.item,
        source: payload.source,
        bytesPerSecond: payload.bytesPerSecond,
        current: payload.current,
        total: payload.total,
      },
      seen: true,
    }
  }

  // 同一个 stage 里没带文件名的事件（例如两个文件之间的间隙）不清掉正在展示的文件；
  // stage 换了（校验、解压、下一段）才说明这次下载已经结束。
  if (state.transfer && state.transfer.stage !== payload.runtimeStage) {
    return { probe: state.probe, transfer: null, seen: state.seen }
  }
  return state
}

/** 格式化时需要的两句词表文案，由调用方用 i18n 提供。 */
export interface NetworkDetailLabels {
  /** 「来源 aliyun」 */
  transferSource: (source: string) => string
  /** 「github 不可用」 */
  probeUnavailable: (source: string) => string
}

function formatProbeEntry(entry: NetworkProbeEntry, labels: NetworkDetailLabels): string {
  if (entry.bytesPerSecond === undefined) return entry.source
  if (entry.bytesPerSecond <= 0) return labels.probeUnavailable(entry.source)
  return `${entry.source} ${formatSpeed(entry.bytesPerSecond)}`
}

/**
 * 把网络细节状态排成进度条下面的行，最多两行。
 *
 * - 测速：「各源实测」+「最终顺序」；只测首字节的源只列源名，失败的源标「不可用」；
 * - 传输：「文件名」+「已下载 / 总量 · 速度 · 来源」。
 *
 * 本次运行还没出现过任何细节时返回 undefined，界面据此不占位。
 */
export function formatNetworkDetails(
  activity: NetworkActivity,
  labels: NetworkDetailLabels
): string[] | undefined {
  if (!activity.seen) return undefined

  const { probe, transfer } = activity
  if (transfer) {
    const parts: string[] = []
    if (transfer.total !== undefined && transfer.total > 0) {
      parts.push(`${formatBytes(transfer.current ?? 0)} / ${formatBytes(transfer.total)}`)
    } else if (transfer.current !== undefined) {
      parts.push(formatBytes(transfer.current))
    }
    if (transfer.bytesPerSecond !== undefined) parts.push(formatSpeed(transfer.bytesPerSecond))
    if (transfer.source) parts.push(labels.transferSource(transfer.source))
    return parts.length > 0 ? [transfer.item, parts.join(' · ')] : [transfer.item]
  }

  if (probe) {
    const lines: string[] = []
    if (probe.entries.length > 0) {
      lines.push(probe.entries.map(entry => formatProbeEntry(entry, labels)).join(' · '))
    }
    if (probe.summary) lines.push(probe.summary)
    return lines
  }

  return []
}
