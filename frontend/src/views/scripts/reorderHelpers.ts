export interface OrderableItem {
  id: string
}

/**
 * 根据排序前的 ID 顺序恢复项目顺序。
 *
 * 使用 sourceOfTruth 中的完整对象按 previousIds 重排，并将 sourceOfTruth 中新增的项目
 *（不在 previousIds 中）按原顺序追加到末尾。这样可以在 API 失败后恢复 UI 顺序，同时
 * 不丢失排序期间新增/删除的项。
 */
export const restoreItemOrder = <T extends OrderableItem>(
  previousIds: string[],
  sourceOfTruth: T[]
): T[] => {
  const idSet = new Set(previousIds)
  const itemMap = new Map(sourceOfTruth.map(item => [item.id, item]))
  const restored: T[] = []

  for (const id of previousIds) {
    const item = itemMap.get(id)
    if (item) restored.push(item)
  }

  for (const item of sourceOfTruth) {
    if (!idSet.has(item.id)) restored.push(item)
  }

  return restored
}

/**
 * 判断两个 ID 数组是否表示相同的顺序。
 */
export const isSameOrder = (a: string[], b: string[]): boolean =>
  a.length === b.length && a.every((id, index) => id === b[index])
