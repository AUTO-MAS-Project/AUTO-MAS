/**
 * Emulator 轮询/防重入/cleanup 测试骨架 (deterministic, fake timers).
 *
 * Subagent C 维护。这些测试不依赖 B 实装，只验证「轮询契约」的形状：
 *  - 进入页面启动轮询，离开页面停止轮询
 *  - 卸载时清理 setInterval
 *  - 重复启动不产生多个 timer
 *  - 空列表不发起轮询请求
 *
 * 当 B 实装 useEmulatorApi / 专区组件后，将这些骨架迁入 composable 测试。
 *
 * 对应 TEST_MATRIX.md 中的 FE-POLL-* 与 FE-CLEANUP-*。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

describe('Emulator 轮询契约骨架 (FE-POLL-01..04)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('setInterval 在 POLLING_INTERVAL=5000ms 触发', () => {
    const cb = vi.fn()
    const id = setInterval(cb, 5000)
    vi.advanceTimersByTime(5000)
    expect(cb).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(5000)
    expect(cb).toHaveBeenCalledTimes(2)
    clearInterval(id)
  })

  it('重复 setInterval 前先 clearInterval，不会叠加', () => {
    const cb = vi.fn()
    const id1 = setInterval(cb, 5000)
    clearInterval(id1)
    const id2 = setInterval(cb, 5000)
    vi.advanceTimersByTime(5000)
    expect(cb).toHaveBeenCalledTimes(1)
    clearInterval(id2)
  })

  it('空列表时不应发起轮询请求（前端 pollDevicesStatus 早退）', () => {
    // 这是契约断言：当 emulatorIndex.length === 0 时，轮询回调应直接 return。
    // B 实装后用挂载组件 + spy getStatusApiEmulatorStatusPost 验证。
    const poll = (index: unknown[]) => {
      if (index.length === 0) return 0
      return 1
    }
    expect(poll([])).toBe(0)
    expect(poll([{}])).toBe(1)
  })

  it('unmount 后 clearInterval 不再触发回调', () => {
    const cb = vi.fn()
    const id = setInterval(cb, 5000)
    clearInterval(id)
    vi.advanceTimersByTime(20000)
    expect(cb).not.toHaveBeenCalled()
  })
})

describe('Emulator per-device in-flight 防重入 (FE-POLL-05)', () => {
  it('同一 deviceKey 的 operate 未完成时再次调用应被忽略', () => {
    // 契约：startingDevices.has(deviceKey) 为 true 时按钮 disabled。
    // B 实装后用挂载组件 + 触发两次 click 验证只发起一次 API。
    const inFlight = new Set<string>()
    const tryStart = (key: string) => {
      if (inFlight.has(key)) return false
      inFlight.add(key)
      return true
    }
    expect(tryStart('emu-1#0')).toBe(true)
    expect(tryStart('emu-1#0')).toBe(false)
    inFlight.delete('emu-1#0')
    expect(tryStart('emu-1#0')).toBe(true)
  })
})

describe('Emulator visibility 路由切换 (FE-POLL-06)', () => {
  it('route.path !== "/emulators" 时 stopPolling 被调用', () => {
    // 契约：watch route.path，进入 /emulators 启动，离开停止。
    const events: string[] = []
    const onPathChange = (path: string) => {
      if (path === '/emulators') events.push('start')
      else events.push('stop')
    }
    onPathChange('/emulators')
    onPathChange('/scripts')
    expect(events).toEqual(['start', 'stop'])
  })
})

describe('Emulator 老板键录制与 Esc/失焦 (FE-BOSS-*)', () => {
  it('录制期间 keydown 收集 Ctrl+Shift+Q，keyup 提交', () => {
    // 复刻 Emulator.vue 当前 handleKeyDown/handleKeyUp 行为契约：
    //  - 修饰键按 Ctrl/Shift/Alt/Meta 顺序收集
    //  - 主键单字符转大写
    //  - keyup 时若 recordedKeys.size > 0 才提交
    const recorded = new Set<string>()
    const onKeyDown = (e: {
      ctrlKey: boolean
      shiftKey: boolean
      altKey: boolean
      metaKey: boolean
      key: string
    }) => {
      const keys: string[] = []
      if (e.ctrlKey) keys.push('Ctrl')
      if (e.shiftKey) keys.push('Shift')
      if (e.altKey) keys.push('Alt')
      if (e.metaKey) keys.push('Meta')
      if (!['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
        keys.push(e.key.length === 1 ? e.key.toUpperCase() : e.key)
      }
      keys.forEach(k => recorded.add(k))
    }
    const onKeyUp = () => {
      if (recorded.size > 0) {
        return Array.from(recorded).join('+')
      }
      return null
    }
    onKeyDown({ ctrlKey: true, shiftKey: true, altKey: false, metaKey: false, key: 'Control' })
    onKeyDown({ ctrlKey: true, shiftKey: true, altKey: false, metaKey: false, key: 'Shift' })
    onKeyDown({ ctrlKey: true, shiftKey: true, altKey: false, metaKey: false, key: 'q' })
    expect(onKeyUp()).toBe('Ctrl+Shift+Q')
  })

  it('未录制主键时 keyup 不提交', () => {
    const recorded = new Set<string>()
    const onKeyUp = () => (recorded.size > 0 ? Array.from(recorded).join('+') : null)
    expect(onKeyUp()).toBeNull()
  })

  it('老板键替换而非追加（单一组合）', () => {
    // 契约：editData.boss_keys = [keyCombo]，长度始终为 1 或 0
    let boss_keys: string[] = []
    const setBossKey = (combo: string) => {
      boss_keys = [combo]
    }
    setBossKey('Ctrl+Q')
    setBossKey('Ctrl+Shift+P')
    expect(boss_keys).toEqual(['Ctrl+Shift+P'])
    expect(boss_keys).toHaveLength(1)
  })
})

describe('Emulator 删除确认与状态清理 (FE-DELETE-*)', () => {
  it('a-popconfirm confirm 才调用 handleDelete', () => {
    // 契约：删除走 a-popconfirm，只有 confirm 事件触发 handleDelete。
    let deleted = false
    const onConfirm = () => {
      deleted = true
    }
    onConfirm()
    expect(deleted).toBe(true)
  })

  it('删除当前激活 Tab 时自动跳转到相邻 Tab', () => {
    // 复刻 Emulator.vue handleDelete 中的 activeKey 切换逻辑：
    //   1. 切换 activeKey 到相邻 Tab（currentIndex+1 优先，否则 currentIndex-1）
    //   2. 随后 loadEmulators() 刷新 index（此处同步删除模拟刷新）
    const index = [{ uid: 'a' }, { uid: 'b' }, { uid: 'c' }]
    let activeKey = 'b'
    const handleDeleteActive = (uid: string) => {
      const currentIndex = index.findIndex(e => e.uid === uid)
      if (currentIndex < index.length - 1) {
        activeKey = index[currentIndex + 1].uid
      } else if (currentIndex > 0) {
        activeKey = index[currentIndex - 1].uid
      } else {
        activeKey = ''
      }
      // 模拟 loadEmulators 后 index 刷新（删除被删项）
      const i = index.findIndex(e => e.uid === uid)
      if (i >= 0) index.splice(i, 1)
    }
    handleDeleteActive('b') // 切到 c，index=[a,c]
    expect(activeKey).toBe('c')
    handleDeleteActive('c') // currentIndex=1 (length-1=1), 走 else 切到 a, index=[a]
    expect(activeKey).toBe('a')
    handleDeleteActive('a') // 唯一一项，activeKey=''
    expect(activeKey).toBe('')
  })
})

describe('Emulator 设备状态映射 (FE-STATUS-*)', () => {
  // 复刻 Emulator.vue getDeviceStatusInfo / canStartDevice / canStopDevice
  const DeviceStatus = {
    ONLINE: 0,
    OFFLINE: 1,
    STARTING: 2,
    CLOSING: 3,
    ERROR: 4,
    NOT_FOUND: 5,
    UNKNOWN: 10,
  } as const

  const getDeviceStatusInfo = (status: number) => {
    switch (status) {
      case DeviceStatus.ONLINE:
        return { text: '在线', color: 'success' }
      case DeviceStatus.OFFLINE:
        return { text: '离线', color: 'default' }
      case DeviceStatus.STARTING:
        return { text: '启动中', color: 'processing' }
      case DeviceStatus.CLOSING:
        return { text: '关闭中', color: 'warning' }
      case DeviceStatus.ERROR:
        return { text: '错误', color: 'error' }
      case DeviceStatus.NOT_FOUND:
        return { text: '未找到', color: 'error' }
      case DeviceStatus.UNKNOWN:
        return { text: '未知', color: 'default' }
      default:
        return { text: '未知', color: 'default' }
    }
  }

  const canStartDevice = (status: number) =>
    status === DeviceStatus.OFFLINE ||
    status === DeviceStatus.ERROR ||
    status === DeviceStatus.NOT_FOUND ||
    status === DeviceStatus.UNKNOWN

  const canStopDevice = (status: number) =>
    status === DeviceStatus.ONLINE || status === DeviceStatus.STARTING

  it('每个状态有唯一 text/color 组合', () => {
    const seen = new Set<string>()
    for (const s of [0, 1, 2, 3, 4, 5, 10, 99]) {
      const info = getDeviceStatusInfo(s)
      const key = `${info.text}|${info.color}`
      // 仅校验有限枚举不重复（'未知' 可能重复，单独处理）
      if (s !== 99 && s !== DeviceStatus.UNKNOWN) {
        expect(seen.has(key)).toBe(false)
        seen.add(key)
      }
    }
  })

  it('ONLINE 与 STARTING 可关闭，其他不可关闭', () => {
    expect(canStopDevice(DeviceStatus.ONLINE)).toBe(true)
    expect(canStopDevice(DeviceStatus.STARTING)).toBe(true)
    expect(canStopDevice(DeviceStatus.OFFLINE)).toBe(false)
    expect(canStopDevice(DeviceStatus.CLOSING)).toBe(false)
    expect(canStopDevice(DeviceStatus.ERROR)).toBe(false)
  })

  it('OFFLINE/ERROR/NOT_FOUND/UNKNOWN 可启动，ONLINE/STARTING/CLOSING 不可', () => {
    expect(canStartDevice(DeviceStatus.OFFLINE)).toBe(true)
    expect(canStartDevice(DeviceStatus.ERROR)).toBe(true)
    expect(canStartDevice(DeviceStatus.NOT_FOUND)).toBe(true)
    expect(canStartDevice(DeviceStatus.UNKNOWN)).toBe(true)
    expect(canStartDevice(DeviceStatus.ONLINE)).toBe(false)
    expect(canStartDevice(DeviceStatus.STARTING)).toBe(false)
    expect(canStartDevice(DeviceStatus.CLOSING)).toBe(false)
  })

  it('ERROR 与 NOT_FOUND 都用 error 色，但 text 不同', () => {
    // 状态不只靠颜色：text 不同保证色盲可读
    expect(getDeviceStatusInfo(DeviceStatus.ERROR).color).toBe('error')
    expect(getDeviceStatusInfo(DeviceStatus.NOT_FOUND).color).toBe('error')
    expect(getDeviceStatusInfo(DeviceStatus.ERROR).text).not.toBe(
      getDeviceStatusInfo(DeviceStatus.NOT_FOUND).text
    )
  })
})

describe('Emulator 空错离线态 (FE-EMPTY-*)', () => {
  it('emulatorIndex 为空时显示空态大按钮，不渲染 Tabs', () => {
    // 契约：v-if emulatorIndex.length === 0 显示 empty-state-large；
    // v-else 渲染 a-tabs。B 实装后用 mount 验证。
    const render = (index: unknown[]) => (index.length === 0 ? 'empty' : 'tabs')
    expect(render([])).toBe('empty')
    expect(render([{}])).toBe('tabs')
  })

  it('devicesData 为空对象时显示「暂无设备信息」与启动按钮', () => {
    const render = (devices: Record<string, unknown>) =>
      !devices || Object.keys(devices).length === 0 ? 'empty-devices' : 'grid'
    expect(render({})).toBe('empty-devices')
    expect(render({ '0': {} })).toBe('grid')
  })
})

describe('Emulator 路径被后端纠正 (FE-PATH-*)', () => {
  it('选择路径后保存，若返回路径与输入不同则提示', async () => {
    // 复刻 selectEmulatorPath 中 paths[0] !== newPath 的提示契约
    const selected = 'C:/Program Files/MuMu/uninstall.exe'
    const corrected = 'C:/Program Files/MuMu/MuMuManager.exe'
    expect(selected).not.toBe(corrected)
    // 提示文案: `路径已自动调整: ${selected} -> ${corrected}`
    const msg = `路径已自动调整: ${selected} -> ${corrected}`
    expect(msg).toContain('->')
    expect(msg).toContain(corrected)
  })
})

describe('Emulator 老板键 MuMu 隐藏 (FE-BOSS-MUMU)', () => {
  it('type === mumu 时不渲染老板键输入框，显示提示文本', () => {
    // 契约：v-if type !== 'mumu' 渲染 a-input；v-else 渲染「MuMu模拟器无需配置老板键」
    const render = (type: string) => (type === 'mumu' ? 'hint' : 'input')
    expect(render('mumu')).toBe('hint')
    expect(render('general')).toBe('input')
    expect(render('ldplayer')).toBe('input')
  })

  it('type === mumu 时显示强力关闭开关', () => {
    const render = (type: string) => (type === 'mumu' ? 'force-kill-switch' : 'none')
    expect(render('mumu')).toBe('force-kill-switch')
    expect(render('general')).toBe('none')
  })
})
