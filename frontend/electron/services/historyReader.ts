import * as fs from 'fs'
import * as path from 'path'
import { DatabaseSync } from 'node:sqlite'

export interface HistoryAttachmentRow {
  id: string
  record_id: string
  kind: string
  role: string
  display_name: string
  relative_path: string | null
  byte_size: number
  available: number
  unavailable_reason: string | null
}

export interface HistoryRecordRow {
  id: string
  time: string
  timestamp: number
  date: string
  username: string
  script_name: string
  status: string
  message: string
  data: string
  log_path: string | null
  log_text_fallback: string | null
  storage_errors: string
  attachments: HistoryAttachmentRow[]
}

/** 只读历史元数据；事务让记录与附件来自同一数据库视图。 */
export function readHistoryRecords(dataRoot: string): HistoryRecordRow[] {
  const databasePath = path.join(dataRoot, 'data', 'history.db')
  if (!fs.existsSync(databasePath)) return []
  const database = new DatabaseSync(databasePath, { readOnly: true })
  try {
    database.exec('BEGIN')
    const records = database
      .prepare(`SELECT id, time, timestamp, date, username, script_name, status, message, data,
        log_path, NULL AS log_text_fallback, storage_errors FROM records ORDER BY timestamp DESC, id DESC`)
      .all() as unknown as HistoryRecordRow[]
    const attachments = database
      .prepare('SELECT * FROM attachments ORDER BY id')
      .all() as unknown as HistoryAttachmentRow[]
    const byRecord = new Map<string, HistoryAttachmentRow[]>()
    for (const attachment of attachments) {
      const group = byRecord.get(attachment.record_id) ?? []
      group.push(attachment)
      byRecord.set(attachment.record_id, group)
    }
    return records.map(record => ({ ...record, attachments: byRecord.get(record.id) ?? [] }))
  } finally {
    database.close()
  }
}

/** 数据库中的相对路径须限制在归档根内。 */
export function historyFilePath(dataRoot: string, relativePath: string | null): string | undefined {
  if (!relativePath || path.isAbsolute(relativePath)) return undefined
  const archiveRoot = path.resolve(dataRoot, 'history')
  const candidate = path.resolve(archiveRoot, relativePath)
  const relative = path.relative(archiveRoot, candidate)
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) return undefined
  try {
    return fs.statSync(candidate).isFile() ? candidate : undefined
  } catch {
    return undefined
  }
}

export function historyLogText(dataRoot: string, record: HistoryRecordRow): string | undefined {
  const log = historyFilePath(dataRoot, record.log_path)
  if (log) {
    try {
      return fs.readFileSync(log, 'utf8')
    } catch {
      // 文件不可读时仍可使用数据库内的完整兜底。
    }
  }
  const database = new DatabaseSync(path.join(dataRoot, 'data', 'history.db'), { readOnly: true })
  try {
    const row = database
      .prepare('SELECT log_text_fallback FROM records WHERE id = ?')
      .get(record.id)
    return typeof row?.log_text_fallback === 'string' ? row.log_text_fallback : undefined
  } finally {
    database.close()
  }
}

/** JSON 仅供问题包阅读，不在导出端重新计算统计或判断执行成败。 */
export function historyRecordJson(record: HistoryRecordRow): Record<string, unknown> {
  return {
    ...record,
    data: JSON.parse(record.data) as unknown,
    storage_errors: JSON.parse(record.storage_errors) as unknown,
    log_text_fallback: undefined,
  }
}
