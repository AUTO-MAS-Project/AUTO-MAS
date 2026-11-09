import { describe, expect, it } from 'vite-plus/test'
import { buildFieldPatch } from './fieldPatch'

describe('field patches', () => {
  it('writes only the requested group and preserves false and null values', () => {
    expect(buildFieldPatch('Info.Status', false)).toEqual({ Info: { Status: false } })
    expect(buildFieldPatch('IfEnabled', null)).toEqual({ IfEnabled: null })
  })

  it('preserves a nested field value without mutating or copying it', () => {
    const value = { selected: ['task-a'], attempts: 0 }
    const patch = buildFieldPatch('Task.Options.Selected', value)
    expect(patch).toEqual({
      Task: { Options: { Selected: { selected: ['task-a'], attempts: 0 } } },
    })
    expect((patch.Task as { Options: { Selected: unknown } }).Options.Selected).toBe(value)
    expect(value).toEqual({ selected: ['task-a'], attempts: 0 })
  })
})
