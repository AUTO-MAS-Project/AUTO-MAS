import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'

// TaskTree 组件纯逻辑测试（不依赖 @vue/test-utils）
// 测试 getStatusColor 函数和 toggleScript 逻辑

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

vi.stubGlobal('window', {
  electronAPI: {
    getLogger: () => logger,
  },
})

// 直接测试 TaskTree 中的 getStatusColor 逻辑（复制自组件源码）
const getStatusColor = (status: string): string => {
  const exactStatusColorMap: Record<string, string> = {
    等待: 'orange',
    排队: 'orange',
    挂起: 'orange',
    运行中: 'blue',
    运行: 'blue',
    进行中: 'blue',
    执行中: 'blue',
    已完成: 'green',
    完成: 'green',
    成功: 'green',
    失败: 'red',
    异常: 'red',
    错误: 'red',
    暂停: 'gray',
    取消: 'default',
    停止: 'default',
  }

  if (exactStatusColorMap[status]) {
    return exactStatusColorMap[status]
  }

  if (/成功|完成|已完成/.test(status)) return 'green'
  if (/失败|错误|异常/.test(status)) return 'red'
  if (/等待|排队|挂起/.test(status)) return 'orange'
  if (/进行|执行|运行/.test(status)) return 'blue'
  if (/暂停|停止/.test(status)) return 'gray'

  return 'default'
}

// 模拟展开/折叠逻辑
const createExpandState = () => {
  const expanded = new Set<string>()

  const toggle = (id: string) => {
    if (expanded.has(id)) {
      expanded.delete(id)
    } else {
      expanded.add(id)
    }
  }

  const expandAll = (ids: string[]) => {
    ids.forEach(id => expanded.add(id))
  }

  const collapseAll = () => {
    expanded.clear()
  }

  return { expanded, toggle, expandAll, collapseAll }
}

describe('TaskTree 纯逻辑', () => {
  describe('getStatusColor', () => {
    it('运行中/运行/进行中/执行中 → blue', () => {
      expect(getStatusColor('运行中')).toBe('blue')
      expect(getStatusColor('运行')).toBe('blue')
      expect(getStatusColor('进行中')).toBe('blue')
      expect(getStatusColor('执行中')).toBe('blue')
    })

    it('已完成/完成/成功 → green', () => {
      expect(getStatusColor('已完成')).toBe('green')
      expect(getStatusColor('完成')).toBe('green')
      expect(getStatusColor('成功')).toBe('green')
    })

    it('失败/错误/异常 → red', () => {
      expect(getStatusColor('失败')).toBe('red')
      expect(getStatusColor('错误')).toBe('red')
      expect(getStatusColor('异常')).toBe('red')
    })

    it('等待/排队/挂起 → orange', () => {
      expect(getStatusColor('等待')).toBe('orange')
      expect(getStatusColor('排队')).toBe('orange')
      expect(getStatusColor('挂起')).toBe('orange')
    })

    it('暂停 → gray', () => {
      expect(getStatusColor('暂停')).toBe('gray')
    })

    it('取消/停止 → default', () => {
      expect(getStatusColor('取消')).toBe('default')
      expect(getStatusColor('停止')).toBe('default')
    })

    it('未知状态 → default', () => {
      expect(getStatusColor('unknown')).toBe('default')
      expect(getStatusColor('')).toBe('default')
    })

    it('模糊匹配：包含"成功"的变体 → green', () => {
      expect(getStatusColor('签到成功')).toBe('green')
      expect(getStatusColor('任务完成啦')).toBe('green')
    })

    it('模糊匹配：包含"失败"的变体 → red', () => {
      expect(getStatusColor('连接失败')).toBe('red')
      expect(getStatusColor('超时错误')).toBe('red')
    })
  })

  describe('展开/折叠逻辑', () => {
    it('toggle 切换单条展开状态', () => {
      const { expanded, toggle } = createExpandState()
      expect(expanded.has('script-1')).toBe(false)

      toggle('script-1')
      expect(expanded.has('script-1')).toBe(true)

      toggle('script-1')
      expect(expanded.has('script-1')).toBe(false)
    })

    it('多条独立 toggle', () => {
      const { expanded, toggle } = createExpandState()

      toggle('script-1')
      toggle('script-2')
      expect(expanded.has('script-1')).toBe(true)
      expect(expanded.has('script-2')).toBe(true)
      expect(expanded.has('script-3')).toBe(false)

      toggle('script-1')
      expect(expanded.has('script-1')).toBe(false)
      expect(expanded.has('script-2')).toBe(true)
    })

    it('expandAll 展开全部', () => {
      const { expanded, expandAll } = createExpandState()
      expandAll(['a', 'b', 'c'])
      expect(expanded.size).toBe(3)
      expect(expanded.has('a')).toBe(true)
      expect(expanded.has('b')).toBe(true)
      expect(expanded.has('c')).toBe(true)
    })

    it('collapseAll 折叠全部', () => {
      const { expanded, expandAll, collapseAll } = createExpandState()
      expandAll(['a', 'b', 'c'])
      expect(expanded.size).toBe(3)

      collapseAll()
      expect(expanded.size).toBe(0)
    })
  })
})
