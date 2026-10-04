import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
const STAMP = '12-00-00'

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
  const history = `history/${DATE}/${USER}/${STAMP}`
  write(`${history}.json`, JSON.stringify({ general_result: 'Success!' }))
  write(`${history}.log`, 'MaaFW 运行\n')
  write(
    `${history}.worker.log`,
    `${workerLogHead}\n资源路径 D:\\AUTO-MAS\\data\\mfw\\${VIEW}\\resource\n`
  )
  write(`${history}.project.log`, '===== debug/go-service.log（本次新增 7 B）=====\nnew go\n')
}

async function entries(): Promise<string[]> {
  const zipPath = path.join(root, 'out.zip')
  const result = await createMaaFWIssueReport(root, zipPath, SCRIPT_ID)
  expect(result.success).toBe(true)
  return new AdmZip(zipPath).getEntries().map(entry => entry.entryName)
}

describe('MFW 问题包收 history 里的 .project.log', () => {
  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'mfw-issue-'))
  })

  afterEach(() => {
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('按后缀认出 .project.log 并放进包里', async () => {
    setUp({ name: 'Demo' }, 'runner 启动')

    expect(await entries()).toContain(
      `scripts/${VIEW}/history/${DATE}/${USER}/${STAMP}.project.log`
    )
  })

  it('有密码输入框、.worker.log 没有打码说明时与 .worker.log 一样不收', async () => {
    setUp(
      { name: 'Demo', option: { Login: { type: 'input', inputs: [{ password: true }] } } },
      'runner 启动'
    )

    const names = await entries()
    expect(names).not.toContain(`scripts/${VIEW}/history/${DATE}/${USER}/${STAMP}.project.log`)
    expect(names).not.toContain(`scripts/${VIEW}/history/${DATE}/${USER}/${STAMP}.worker.log`)
  })

  it('有密码输入框、.worker.log 带打码说明时照收', async () => {
    setUp(
      { name: 'Demo', option: { Login: { type: 'input', inputs: [{ password: true }] } } },
      '[MAS 日志打码] 本次的 .worker.log 与 .maafw.log 已把 1 个密码值换成「<已隐藏>」'
    )

    expect(await entries()).toContain(
      `scripts/${VIEW}/history/${DATE}/${USER}/${STAMP}.project.log`
    )
  })
})
