// 解锁状态仍按北京时间跨日锁回；口令的 30 分钟有效期由主进程校验。
const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000

export function getMysteryDate(date = new Date()): string {
  return new Date(date.getTime() + BEIJING_OFFSET_MS).toISOString().slice(0, 10)
}
