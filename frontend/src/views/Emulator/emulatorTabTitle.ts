/** 只移除自动名称末尾与实际路径相同的部分，保留自定义名称。 */
export function emulatorTabTitle(name: string, path: string): string {
  const normalize = (value: string) => value.replace(/\\/g, '/').toLowerCase()
  const suffix = `(${path})`
  return path && normalize(name).endsWith(normalize(suffix))
    ? name.slice(0, -suffix.length).trim() || name
    : name
}
