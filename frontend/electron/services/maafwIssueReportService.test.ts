import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { DatabaseSync } from 'node:sqlite'
import AdmZip = require('adm-zip')
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { createMaaFWIssueReport } from './maafwIssueReportService'

vi.mock('./logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
}))
vi.mock('./maafwProjectRuntimeProbe', () => ({
  probeProjectRuntime: vi.fn(async () => ({})),
}))

const SCRIPT_ID = '0123456789ab4cdef0123456789abcde'
const VIEW = '0123456789ab'
const USER = '用户A'
const DATE = '2026-09-28'

let root: string

function write(relative: string, text: string): void {
  const target = path.join(root, relative)
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, text, 'utf-8')
}

function setUp(interfaceJson: object, workerLogHead: string): void {
  write(
    'config/ScriptConfig.json',
    JSON.stringify({
      instances: [{ uid: SCRIPT_ID, type: 'MaaFWConfig' }],
      [SCRIPT_ID]: {
        Info: { Name: 'Demo' },
        SubConfigsInfo: {
          UserData: { instances: [{ uid: 'u1' }], u1: { Info: { Name: USER } } },
        },
      },
    })
  )
  write(`data/mfw/${VIEW}/interface.json`, JSON.stringify(interfaceJson))
  const history = `history/${DATE}/1`
  write(`${history}/0.log`, 'MaaFW 运行\n')
  write(
    `${history}/1.log`,
    `${workerLogHead}\n资源路径 D:\\AUTO-MAS\\data\\mfw\\${VIEW}\\resource\n`
  )
  write(`${history}/2.log`, '===== debug/go-service.log（本次新增 7 B）=====\nnew go\n')
  const db = new DatabaseSync(path.join(root, 'data', 'history.db'))
  try {
    db.exec(`CREATE TABLE records(id INTEGER PRIMARY KEY, time TEXT, timestamp REAL, date TEXT,
      username TEXT, script_name TEXT, status TEXT, message TEXT, data TEXT, log_path TEXT,
      log_text_fallback TEXT, storage_errors TEXT);
      CREATE TABLE attachments(id INTEGER PRIMARY KEY, record_id INTEGER, kind TEXT, role TEXT,
      display_name TEXT, relative_path TEXT, byte_size INTEGER, available INTEGER, unavailable_reason TEXT);`)
    db.prepare('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)').run(
      1,
      `${DATE}T12:00:00+04:00`,
      Date.parse(`${DATE}T12:00:00+04:00`) / 1000,
      DATE,
      USER,
      'Demo',
      'success',
      'Success!',
      '{}',
      `${DATE}/1/0.log`,
      null,
      '[]'
    )
    const insert = db.prepare('INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?)')
    insert.run(1, 1, 'log', 'worker_log', 'worker.log', `${DATE}/1/1.log`, 100, 1, null)
    insert.run(2, 1, 'log', 'project_log', 'project.log', `${DATE}/1/2.log`, 100, 1, null)
  } finally {
    db.close()
  }
}

async function entries(): Promise<string[]> {
  const zipPath = path.join(root, 'out.zip')
  const result = await createMaaFWIssueReport(root, zipPath, SCRIPT_ID)
  expect(result.success).toBe(true)
  return new AdmZip(zipPath).getEntries().map(entry => entry.entryName)
}

describe('MFW 问题包按 SQLite 附件用途收项目日志', () => {
  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'mfw-issue-'))
  })

  afterEach(() => {
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('按附件用途认出项目日志并放进包里', async () => {
    setUp({ name: 'Demo' }, 'runner 启动')

    expect(await entries()).toContain(`scripts/${VIEW}/history/${DATE}/1/2.log`)
  })

  it('有密码输入框、.worker.log 没有打码说明时与 .worker.log 一样不收', async () => {
    setUp(
      { name: 'Demo', option: { Login: { type: 'input', inputs: [{ password: true }] } } },
      'runner 启动'
    )

    const names = await entries()
    expect(names).not.toContain(`scripts/${VIEW}/history/${DATE}/1/2.log`)
    expect(names).not.toContain(`scripts/${VIEW}/history/${DATE}/1/1.log`)
  })

  it('有密码输入框、.worker.log 带打码说明时照收', async () => {
    setUp(
      { name: 'Demo', option: { Login: { type: 'input', inputs: [{ password: true }] } } },
      '[MAS 日志打码] 本次的 .worker.log 与 .maafw.log 已把 1 个密码值换成「<已隐藏>」'
    )

    expect(await entries()).toContain(`scripts/${VIEW}/history/${DATE}/1/2.log`)
  })
})
