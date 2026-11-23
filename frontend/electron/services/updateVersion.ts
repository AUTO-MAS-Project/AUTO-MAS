interface ParsedVersion {
  release: number[]
  /** 无预发布段时为 null；正式版排在同号预发布版之前 */
  pre: (number | string)[] | null
}

function parseVersion(raw: string): ParsedVersion {
  // 将版本文本拆解为主版本数字段和可比较的预发布标识，供应用更新排序使用。
  const text = raw.trim().replace(/^v/i, '')
  const [main, ...rest] = text.split('-')
  const release = main.split('.').map(part => {
    // 把主版本分段转换为整数，无法解析的分段按零处理。
    const n = Number.parseInt(part, 10)
    return Number.isNaN(n) ? 0 : n
  })
  if (rest.length === 0) return { release, pre: null }
  const pre = rest
    .join('-')
    .split(/[.-]/)
    .filter(part => /* 过滤预发布号拆分后产生的空标识。 */ part.length > 0)
    .map(part =>
      /* 将纯数字预发布标识转换为数值，其余文本统一大小写后参与比较。 */ /^\d+$/.test(part)
        ? Number.parseInt(part, 10)
        : part.toLowerCase()
    )
  return { release, pre }
}

function compareIdentifiers(a: number | string, b: number | string): number {
  // 比较单个预发布标识，数字按数值排序且排在文本之前。
  if (typeof a === 'number' && typeof b === 'number') return a - b
  // 数字标识符排在字母标识符之前（与 semver 一致）
  if (typeof a === 'number') return -1
  if (typeof b === 'number') return 1
  return a < b ? -1 : a > b ? 1 : 0
}

/** 版本号升序比较：a < b 返回负数。beta.10 大于 beta.2，正式版大于同号预发布版。 */
export function compareVersions(a: string, b: string): number {
  // 依次比较主版本和预发布标识，正式版高于同号预发布版，返回小于、等于或大于零的比较结果。
  const pa = parseVersion(a)
  const pb = parseVersion(b)
  const len = Math.max(pa.release.length, pb.release.length)
  for (let i = 0; i < len; i += 1) {
    const diff = (pa.release[i] ?? 0) - (pb.release[i] ?? 0)
    if (diff !== 0) return diff
  }
  if (pa.pre === null && pb.pre === null) return 0
  if (pa.pre === null) return 1
  if (pb.pre === null) return -1
  const preLen = Math.max(pa.pre.length, pb.pre.length)
  for (let i = 0; i < preLen; i += 1) {
    const ia = pa.pre[i]
    const ib = pb.pre[i]
    if (ia === undefined) return -1
    if (ib === undefined) return 1
    const diff = compareIdentifiers(ia, ib)
    if (diff !== 0) return diff
  }
  return 0
}
