import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'

import {
  MAAFW_DUPLICATE_TASK_SEPARATOR,
  buildMaaFWTaskInstanceId,
  resolveMaaFWTaskName,
} from './maafwTaskInstance'

const copyOf = (taskName: string, suffix: string) =>
  `${taskName}${MAAFW_DUPLICATE_TASK_SEPARATOR}${suffix}`

describe('resolveMaaFWTaskName', () => {
  it('裸任务名解析为自身', () => {
    expect(resolveMaaFWTaskName('战斗', new Set(['战斗']))).toBe('战斗')
  })

  it('副本 id 解析回任务名', () => {
    expect(resolveMaaFWTaskName(copyOf('战斗', 'ab12cd34'), new Set(['战斗']))).toBe('战斗')
  })

  it('任务名自身含分隔符时按原名解析', () => {
    const weirdName = copyOf('战斗', 'literal')
    expect(resolveMaaFWTaskName(weirdName, new Set(['战斗', weirdName]))).toBe(weirdName)
  })

  it('前缀不是已知任务名时原样返回', () => {
    const unknown = copyOf('不存在的任务', 'ab12cd34')
    expect(resolveMaaFWTaskName(unknown, new Set(['战斗']))).toBe(unknown)
  })

  it('分隔符在开头时不切出空任务名', () => {
    const leading = `${MAAFW_DUPLICATE_TASK_SEPARATOR}ab12cd34`
    expect(resolveMaaFWTaskName(leading, new Set(['战斗']))).toBe(leading)
  })
})

describe('buildMaaFWTaskInstanceId', () => {
  it('队列里还没有该任务时用裸任务名', () => {
    expect(buildMaaFWTaskInstanceId('战斗', new Set())).toBe('战斗')
  })

  it('已有首份时生成带后缀的副本 id', () => {
    const taskId = buildMaaFWTaskInstanceId('战斗', new Set(['战斗']))
    expect(taskId).not.toBe('战斗')
    expect(taskId.startsWith(`战斗${MAAFW_DUPLICATE_TASK_SEPARATOR}`)).toBe(true)
    expect(resolveMaaFWTaskName(taskId, new Set(['战斗']))).toBe('战斗')
  })

  it('避开已被占用的副本 id', () => {
    const used = new Set(['战斗'])
    const first = buildMaaFWTaskInstanceId('战斗', used)
    used.add(first)
    const second = buildMaaFWTaskInstanceId('战斗', used)
    expect(second).not.toBe(first)
    expect(resolveMaaFWTaskName(second, new Set(['战斗']))).toBe('战斗')
  })

  it('随机后缀撞上已有 id 时会继续换一个', () => {
    const randomSpy = vi
      .spyOn(Math, 'random')
      .mockReturnValueOnce(0.5)
      .mockReturnValueOnce(0.5)
      .mockReturnValue(0.7)
    const first = buildMaaFWTaskInstanceId('战斗', new Set(['战斗']))
    const second = buildMaaFWTaskInstanceId('战斗', new Set(['战斗', first]))
    expect(second).not.toBe(first)
    randomSpy.mockRestore()
  })

  it('任务名自身含分隔符时，它的副本仍解析回该任务名', () => {
    const weirdName = copyOf('战斗', 'literal')
    const copyId = buildMaaFWTaskInstanceId(weirdName, new Set([weirdName]))
    expect(copyId).not.toBe(weirdName)
    expect(resolveMaaFWTaskName(copyId, new Set(['战斗', weirdName]))).toBe(weirdName)
  })
})

describe('前后端分隔符契约', () => {
  it('与后端 DUPLICATE_TASK_SUFFIX_SEPARATOR 字面一致', () => {
    const modelsPath = fileURLToPath(
      new URL(
        '../../../app/task/MaaFW/tools/core/automas_maafw_interface/models.py',
        import.meta.url
      )
    )
    const source = readFileSync(modelsPath, 'utf8')
    const matched = source.match(/DUPLICATE_TASK_SUFFIX_SEPARATOR = "([^"]+)"/)
    expect(matched?.[1]).toBe(MAAFW_DUPLICATE_TASK_SEPARATOR)
  })
})
