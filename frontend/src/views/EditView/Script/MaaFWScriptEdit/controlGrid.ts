// 控制配置各格的栅格宽度：窄屏一列；中等宽度每行两格、单数格时最后一行三格；宽屏每行最多
// 三格。任何格数下最后一行都不留单格（只有一格时除外）。

export interface ControlGridCol {
  xs: number
  md: number
  xl: number
}

// 每行格数换成每格的栅格宽度
const spansOf = (rows: number[]): number[] =>
  rows.flatMap(size => Array<number>(size).fill(24 / size))

// 余两格时最后一行两格（8 格 = 3 / 3 / 2），余一格时最后两行各两格（7 格 = 3 / 2 / 2）
const wideRowSpans = (count: number): number[] => {
  const rows: number[] = []
  let rest = count
  while (rest > 0) {
    const size = rest === 4 ? 2 : Math.min(rest, 3)
    rows.push(size)
    rest -= size
  }
  return spansOf(rows)
}

// 7 格 = 2 / 2 / 3，9 格 = 2 / 2 / 2 / 3
const mediumRowSpans = (count: number): number[] => {
  const rows: number[] = []
  let rest = count
  while (rest > 0) {
    const size = rest === 3 ? 3 : Math.min(rest, 2)
    rows.push(size)
    rest -= size
  }
  return spansOf(rows)
}

/** 按顺序给出 count 格各自的栅格宽度 */
export function gridCols(count: number): ControlGridCol[] {
  const medium = mediumRowSpans(count)
  const wide = wideRowSpans(count)
  return medium.map((md, index) => ({ xs: 24, md, xl: wide[index]! }))
}

/** 按字段顺序排格：返回取某字段栅格宽度的函数，不在列表里的字段返回整行 */
export function fieldCols<T extends string>(fields: readonly T[]) {
  const cols = gridCols(fields.length)
  return (field: T): ControlGridCol => cols[fields.indexOf(field)] ?? { xs: 24, md: 24, xl: 24 }
}
