import { describe, expect, it } from 'vitest'
import { isSameOrder, restoreItemOrder } from './reorderHelpers'

describe('reorderHelpers: restoreItemOrder', () => {
  it('restores previous order from source of truth', () => {
    const previousIds = ['a', 'b', 'c']
    const sourceOfTruth = [
      { id: 'b', name: 'B' },
      { id: 'c', name: 'C' },
      { id: 'a', name: 'A' },
    ]

    const restored = restoreItemOrder(previousIds, sourceOfTruth)

    expect(restored.map(item => item.id)).toEqual(['a', 'b', 'c'])
    // 确认返回的是 sourceOfTruth 中的同一对象引用
    expect(restored[0]).toBe(sourceOfTruth[2])
    expect(restored[1]).toBe(sourceOfTruth[0])
    expect(restored[2]).toBe(sourceOfTruth[1])
  })

  it('appends newly added items at the end', () => {
    const previousIds = ['a', 'b']
    const sourceOfTruth = [
      { id: 'a', name: 'A' },
      { id: 'c', name: 'C' },
      { id: 'b', name: 'B' },
    ]

    const restored = restoreItemOrder(previousIds, sourceOfTruth)

    expect(restored.map(item => item.id)).toEqual(['a', 'b', 'c'])
    expect(restored[2]).toBe(sourceOfTruth[1])
  })

  it('skips deleted items that are no longer in source of truth', () => {
    const previousIds = ['a', 'b', 'c']
    const sourceOfTruth = [
      { id: 'a', name: 'A' },
      { id: 'c', name: 'C' },
    ]

    const restored = restoreItemOrder(previousIds, sourceOfTruth)

    expect(restored.map(item => item.id)).toEqual(['a', 'c'])
  })

  it('returns source of truth order when previousIds is empty', () => {
    const sourceOfTruth = [
      { id: 'a', name: 'A' },
      { id: 'b', name: 'B' },
    ]

    const restored = restoreItemOrder([], sourceOfTruth)

    expect(restored.map(item => item.id)).toEqual(['a', 'b'])
  })

  it('returns empty array when source of truth is empty', () => {
    expect(restoreItemOrder(['a', 'b'], [])).toEqual([])
  })
})

describe('reorderHelpers: isSameOrder', () => {
  it('returns true for identical arrays', () => {
    expect(isSameOrder(['a', 'b', 'c'], ['a', 'b', 'c'])).toBe(true)
  })

  it('returns false for different lengths', () => {
    expect(isSameOrder(['a', 'b'], ['a', 'b', 'c'])).toBe(false)
  })

  it('returns false for different order', () => {
    expect(isSameOrder(['a', 'b', 'c'], ['c', 'b', 'a'])).toBe(false)
  })

  it('returns true for empty arrays', () => {
    expect(isSameOrder([], [])).toBe(true)
  })
})
