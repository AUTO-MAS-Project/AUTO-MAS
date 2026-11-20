// 每日口令由后端派生与校验，前端只保留北京时间换算，用于跨日自动锁回。
const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000

export function getMysteryDate(date = new Date()): string {
  return new Date(date.getTime() + BEIJING_OFFSET_MS).toISOString().slice(0, 10)
}
