/** 只构造字段补丁；字段别名、序列化和保存顺序由调用方处理。 */
export function buildFieldPatch(key: string, value: unknown): Record<string, unknown> {
  const parts = key.split('.')
  const patch: Record<string, unknown> = {}
  let current = patch
  for (const part of parts.slice(0, -1)) {
    const nested: Record<string, unknown> = {}
    current[part] = nested
    current = nested
  }
  current[parts[parts.length - 1]] = value
  return patch
}
