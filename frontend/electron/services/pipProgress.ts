/**
 * pip 安装输出进度解析（#499）
 *
 * pip 在管道模式下只按包打印「Downloading xxx (9.4 MB)」，没有逐字节回报，
 * 因此按「已完成下载的字节数 / 总字节数」推进 40-88 的进度段；解析不到字节
 * 时回退旧的包数锚点（Installing collected packages: 视为 80）。
 */

export type PipPhase = 'resolving' | 'installing' | 'done'

export interface PipProgressState {
  phase: PipPhase
  totalBytes: number
  downloadedBytes: number
  totalPackages: number
  pendingBytes: number
  lineBuf: string
  /** 已达到过的最大完成比例，保证进度不因新一轮下载而倒退 */
  maxRatio: number
}

const DOWNLOAD_RE = /(?:Downloading|Using cached)\s+\S+\s+\(([\d.]+)\s*(B|bytes|kB|MB|GB|TB)\)/
const COLLECTING_RE = /^Collecting\s+\S+/
const INSTALLING_RE = /^Installing collected packages:/
const DONE_RE = /^Successfully installed/

const UNIT_BYTES: Record<string, number> = {
  B: 1,
  bytes: 1,
  kB: 1024,
  MB: 1024 ** 2,
  GB: 1024 ** 3,
  TB: 1024 ** 4,
}

export function createPipProgressState(): PipProgressState {
  return {
    phase: 'resolving',
    totalBytes: 0,
    downloadedBytes: 0,
    totalPackages: 0,
    pendingBytes: 0,
    lineBuf: '',
    maxRatio: 0,
  }
}

function completePending(state: PipProgressState): void {
  state.downloadedBytes += state.pendingBytes
  state.pendingBytes = 0
}

function feedLine(state: PipProgressState, line: string): void {
  if (DONE_RE.test(line)) {
    completePending(state)
    state.phase = 'done'
    return
  }
  if (INSTALLING_RE.test(line)) {
    completePending(state)
    state.phase = 'installing'
    return
  }
  const download = DOWNLOAD_RE.exec(line)
  if (download) {
    completePending(state)
    const size = Number.parseFloat(download[1] ?? '0') * (UNIT_BYTES[download[2]] ?? 0)
    state.totalBytes += size
    if (line.includes('Using cached')) {
      // 命中缓存几乎不耗时，直接计入已完成
      state.downloadedBytes += size
    } else {
      state.pendingBytes = size
    }
    return
  }
  if (COLLECTING_RE.test(line)) {
    state.totalPackages += 1
    completePending(state)
  }
}

function updateMaxRatio(state: PipProgressState): void {
  if (state.totalBytes > 0) {
    state.maxRatio = Math.max(state.maxRatio, Math.min(state.downloadedBytes / state.totalBytes, 1))
  }
}

/** 喂入一段 pip stdout（可为任意切分的 chunk），按行解析。 */
export function feedPipOutput(state: PipProgressState, chunk: string): void {
  state.lineBuf += chunk
  const lines = state.lineBuf.split(/\r?\n/)
  state.lineBuf = lines.pop() ?? ''
  for (const line of lines) feedLine(state, line)
  updateMaxRatio(state)
}

/** 流结束时冲掉缓冲里的最后一行（pip 输出可能不以换行结尾）。 */
export function flushPipOutput(state: PipProgressState): void {
  if (state.lineBuf) {
    const rest = state.lineBuf
    state.lineBuf = ''
    feedLine(state, rest)
  }
  updateMaxRatio(state)
}

/**
 * 当前进度百分比：下载段 40-88 随已完成字节推进，installing ≥90
 * （无字节信息时回退旧锚点 80），成功 95。
 */
export function pipProgressPercent(state: PipProgressState): number {
  if (state.phase === 'done') return 95
  if (state.phase === 'installing') {
    if (state.totalBytes === 0) return 80
    return Math.round(Math.max(90, 40 + state.maxRatio * 48))
  }
  return Math.round(40 + state.maxRatio * 48)
}
