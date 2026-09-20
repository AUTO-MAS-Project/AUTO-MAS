import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import AdmZip = require('adm-zip')
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CollectorState, addRecentFailedMaaEndHistoryLogs } from './issueReportCore'

vi.mock('./logger', () => ({
  getLogger: () => ({ debug: vi.fn() }),
}))

const tempRoots: string[] = []

afterEach(() => {
  for (const tempRoot of tempRoots.splice(0)) {
    fs.rmSync(tempRoot, { recursive: true, force: true })
  }
})

function writeHistoryRecord(
  dataRoot: string,
  name: string,
  result: string,
  timestamp: number
): void {
  const recordDir = path.join(dataRoot, 'history', '2026-09-19', '终末地-日常')
  fs.mkdirSync(recordDir, { recursive: true })
  const basePath = path.join(recordDir, name)
  fs.writeFileSync(`${basePath}.log`, `${name} stdout`, 'utf8')
  fs.writeFileSync(`${basePath}.json`, JSON.stringify({ maaend_result: result }), 'utf8')
  fs.utimesSync(`${basePath}.log`, timestamp, timestamp)
  fs.utimesSync(`${basePath}.json`, timestamp, timestamp)
}

describe('addRecentFailedMaaEndHistoryLogs', () => {
  it('adds the latest three failed MaaEnd records with log and json files', () => {
    const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-issue-report-'))
    tempRoots.push(dataRoot)
    writeHistoryRecord(dataRoot, 'MaaEnd-00-01-00', 'MaaEnd 进程超时', 1)
    writeHistoryRecord(dataRoot, 'MaaEnd-00-02-00', '[日常] Success!', 2)
    writeHistoryRecord(dataRoot, 'MaaEnd-00-03-00', '[日常] 未捕获到日志', 3)
    writeHistoryRecord(dataRoot, 'MaaEnd-00-04-00', '[日常] MaaEnd 任务启动失败', 4)
    writeHistoryRecord(dataRoot, 'MaaEnd-00-05-00', '[日常] MaaEnd 部分任务执行失败', 5)
    fs.writeFileSync(
      path.join(dataRoot, 'history', '2026-09-19', '终末地-日常', 'Other-00-06-00.json'),
      JSON.stringify({ result: '失败' }),
      'utf8'
    )

    const state: CollectorState = { zip: new AdmZip(), entries: [], archiveBytes: 0 }
    const addedPaths = addRecentFailedMaaEndHistoryLogs(state, [dataRoot])

    expect(addedPaths).toEqual([
      'logs/mas-history/2026-09-19/终末地-日常/MaaEnd-00-05-00.log',
      'logs/mas-history/2026-09-19/终末地-日常/MaaEnd-00-05-00.json',
      'logs/mas-history/2026-09-19/终末地-日常/MaaEnd-00-04-00.log',
      'logs/mas-history/2026-09-19/终末地-日常/MaaEnd-00-04-00.json',
      'logs/mas-history/2026-09-19/终末地-日常/MaaEnd-00-03-00.log',
      'logs/mas-history/2026-09-19/终末地-日常/MaaEnd-00-03-00.json',
    ])
    expect(state.zip.getEntries().map(entry => entry.entryName)).toEqual(addedPaths)
  })
})
