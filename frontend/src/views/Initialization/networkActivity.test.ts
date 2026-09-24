import { describe, expect, it } from 'vitest'
import {
  EMPTY_NETWORK_ACTIVITY,
  NETWORK_PROBE_STAGE,
  formatNetworkDetails,
  reduceNetworkActivity,
} from './networkActivity'
import type { NetworkActivity, NetworkDetailLabels } from './networkActivity'

function probeRunning(source: string, bytesPerSecond?: number) {
  return { runtimeStage: NETWORK_PROBE_STAGE, runtimeStatus: 'running', source, bytesPerSecond }
}

function probeDone(message: string) {
  return { runtimeStage: NETWORK_PROBE_STAGE, runtimeStatus: 'succeeded', message }
}

const download = {
  runtimeStage: 'uv.download',
  runtimeStatus: 'running',
  item: 'uv-x86_64-pc-windows-msvc.zip',
  source: 'aliyun',
  bytesPerSecond: 3355443,
  current: 9437184,
  total: 18874368,
}

const labels: NetworkDetailLabels = {
  transferSource: source => `来源 ${source}`,
  probeUnavailable: source => `${source} 不可用`,
}

describe('reduceNetworkActivity', () => {
  it('旧链路与旧版 Runtime 的进度没有这些字段，状态原样不动', () => {
    const state = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, {
      runtimeStage: 'workspace.clone',
      runtimeStatus: 'running',
    })
    expect(state).toBe(EMPTY_NETWORK_ACTIVITY)
    expect(reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, {})).toBe(EMPTY_NETWORK_ACTIVITY)
  })

  it('测速按到达顺序累积，同一个源再来一次就地替换，succeeded 记下最终顺序并保留列表', () => {
    let state: NetworkActivity = EMPTY_NETWORK_ACTIVITY
    state = reduceNetworkActivity(state, probeRunning('aliyun', 3355443))
    state = reduceNetworkActivity(state, probeRunning('github', 0))
    state = reduceNetworkActivity(state, probeRunning('cnb', 2202010))
    state = reduceNetworkActivity(state, probeRunning('github', 524288))

    expect(state.probe).toEqual({
      entries: [
        { source: 'aliyun', bytesPerSecond: 3355443 },
        { source: 'github', bytesPerSecond: 524288 },
        { source: 'cnb', bytesPerSecond: 2202010 },
      ],
      summary: null,
    })
    expect(state.seen).toBe(true)

    state = reduceNetworkActivity(state, probeDone('uv 源顺序：aliyun → cnb → github'))
    expect(state.probe?.summary).toBe('uv 源顺序：aliyun → cnb → github')
    expect(state.probe?.entries).toHaveLength(3)
  })

  it('只测首字节的源（git 类）不带速度，按缺失记而不是按 0 记', () => {
    const state = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, probeRunning('github'))
    expect(state.probe?.entries).toEqual([{ source: 'github', bytesPerSecond: undefined }])
    expect(state.probe?.entries[0].bytesPerSecond).toBeUndefined()
  })

  it('上一轮收口后再来的测速属于新一轮，不和旧列表混在一起', () => {
    let state: NetworkActivity = EMPTY_NETWORK_ACTIVITY
    state = reduceNetworkActivity(state, probeRunning('aliyun', 3355443))
    state = reduceNetworkActivity(state, probeDone('uv 源顺序：aliyun'))
    state = reduceNetworkActivity(state, probeRunning('gh-proxy', 2097152))

    expect(state.probe).toEqual({
      entries: [{ source: 'gh-proxy', bytesPerSecond: 2097152 }],
      summary: null,
    })

    // 没有 running 直接 succeeded 的一轮也是空列表 + 新文案
    state = reduceNetworkActivity(state, probeDone('python 源顺序：gh-proxy'))
    state = reduceNetworkActivity(state, probeDone('package-index 源顺序：无'))
    expect(state.probe).toEqual({ entries: [], summary: 'package-index 源顺序：无' })
  })

  it('pending 之类的测速事件不改状态', () => {
    const state = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, {
      runtimeStage: NETWORK_PROBE_STAGE,
      runtimeStatus: 'pending',
      source: 'aliyun',
    })
    expect(state).toBe(EMPTY_NETWORK_ACTIVITY)
  })

  it('带文件名的进度换成传输细节并清掉测速列表', () => {
    let state: NetworkActivity = EMPTY_NETWORK_ACTIVITY
    state = reduceNetworkActivity(state, probeRunning('aliyun', 3355443))
    state = reduceNetworkActivity(state, download)

    expect(state).toEqual({
      probe: null,
      transfer: {
        stage: 'uv.download',
        item: 'uv-x86_64-pc-windows-msvc.zip',
        source: 'aliyun',
        bytesPerSecond: 3355443,
        current: 9437184,
        total: 18874368,
      },
      seen: true,
    })
  })

  it('同一 stage 里没带文件名的事件不清传输细节，换了 stage 才清，seen 保持', () => {
    let state = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, download)
    const kept = reduceNetworkActivity(state, {
      runtimeStage: 'uv.download',
      runtimeStatus: 'running',
    })
    expect(kept).toBe(state)

    state = reduceNetworkActivity(state, { runtimeStage: 'uv.verify', runtimeStatus: 'succeeded' })
    expect(state.transfer).toBeNull()
    expect(state.seen).toBe(true)
  })

  it('桥接合成的段收口（没有 runtimeStage）也会清掉传输细节', () => {
    const state = reduceNetworkActivity(reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, download), {})
    expect(state.transfer).toBeNull()
  })

  it('测速开始时清掉上一次的传输细节', () => {
    const state = reduceNetworkActivity(
      reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, download),
      probeRunning('pypi', 419430)
    )
    expect(state.transfer).toBeNull()
    expect(state.probe?.entries).toEqual([{ source: 'pypi', bytesPerSecond: 419430 }])
  })
})

describe('formatNetworkDetails', () => {
  it('一次都没出现过细节时返回 undefined，界面不占位', () => {
    expect(formatNetworkDetails(EMPTY_NETWORK_ACTIVITY, labels)).toBeUndefined()
    const untouched = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, {
      runtimeStage: 'workspace.clone',
      runtimeStatus: 'running',
    })
    expect(formatNetworkDetails(untouched, labels)).toBeUndefined()
  })

  it('首条细节之后返回数组，之后即使细节清空也保持数组', () => {
    let state = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, download)
    expect(formatNetworkDetails(state, labels)).toEqual([
      'uv-x86_64-pc-windows-msvc.zip',
      '9 MB / 18 MB · 3.2 MB/s · 来源 aliyun',
    ])

    state = reduceNetworkActivity(state, { runtimeStage: 'uv.verify', runtimeStatus: 'succeeded' })
    expect(formatNetworkDetails(state, labels)).toEqual([])

    state = reduceNetworkActivity(state, {
      runtimeStage: 'workspace.clone',
      runtimeStatus: 'running',
    })
    expect(formatNetworkDetails(state, labels)).toEqual([])
  })

  it('测速三种取值三种写法：正数带速度、缺失只列源名、0 标不可用', () => {
    let state: NetworkActivity = EMPTY_NETWORK_ACTIVITY
    state = reduceNetworkActivity(state, probeRunning('github'))
    state = reduceNetworkActivity(state, probeRunning('cnb'))
    expect(formatNetworkDetails(state, labels)).toEqual(['github · cnb'])

    state = reduceNetworkActivity(state, probeDone('git 源顺序：github → cnb'))
    expect(formatNetworkDetails(state, labels)).toEqual([
      'github · cnb',
      'git 源顺序：github → cnb',
    ])

    state = reduceNetworkActivity(state, probeRunning('astral', 8854451))
    state = reduceNetworkActivity(state, probeRunning('gh-proxy', 0))
    expect(formatNetworkDetails(state, labels)).toEqual(['astral 8.4 MB/s · gh-proxy 不可用'])
  })

  it('传输细节没有总量时只写已下载量，没有任何数字时只写文件名', () => {
    const partial = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, {
      runtimeStage: 'python.install',
      item: 'cpython.tar.gz',
      current: 1048576,
    })
    expect(formatNetworkDetails(partial, labels)).toEqual(['cpython.tar.gz', '1 MB'])

    const bare = reduceNetworkActivity(EMPTY_NETWORK_ACTIVITY, {
      runtimeStage: 'python.install',
      item: 'cpython.tar.gz',
    })
    expect(formatNetworkDetails(bare, labels)).toEqual(['cpython.tar.gz'])
  })
})
