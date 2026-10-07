import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import * as ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'

const source = readFileSync(new URL('./ConfigRestoreSection.vue', import.meta.url), 'utf8')
const descriptor = parse(source, { filename: 'ConfigRestoreSection.vue' }).descriptor

// 提取页面实际回调，在真实 Vue 响应式状态下验证预览结果。
const script = descriptor.scriptSetup?.content ?? ''
const scriptFile = ts.createSourceFile(
  'ConfigRestoreSection.ts',
  script,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TS
)

const extractVariable = (name: string): string => {
  let result = ''
  const visit = (node: ts.Node): void => {
    if (ts.isVariableStatement(node)) {
      const found = node.declarationList.declarations.some(
        declaration => ts.isIdentifier(declaration.name) && declaration.name.text === name
      )
      if (found) result = script.slice(node.getStart(scriptFile), node.getEnd())
    }
    ts.forEachChild(node, visit)
  }
  visit(scriptFile)
  if (!result) throw new Error(`未找到 ${name} 源码`)
  return result
}

const callbackJavaScript = ts.transpileModule(
  `${extractVariable('formatBackupTime')}
${extractVariable('handlePreview')}`,
  {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
    },
  }
).outputText

type PreviewPayload = {
  code?: number
  message?: string
  data?: Record<string, unknown> | null
  info?: { key: string; value: string }[]
  account?: { key: string; value: string }[]
  tasks?: { app_id: string; app_name: string; enabled: boolean }[]
  instances?: unknown[]
  warnings?: unknown
  restoreAllowed?: unknown
}

const createRuntime = (preview: () => Promise<PreviewPayload>) => {
  const props = { api: { preview } }
  const restoreTarget = Vue.ref('onedragon')
  const previewOpen = Vue.ref(false)
  const previewLoading = Vue.ref(false)
  const previewError = Vue.ref('')
  const previewTime = Vue.ref('')
  const previewItem = Vue.ref<{ time: string } | null>(null)
  const previewWarnings = Vue.ref<string[]>([])
  const previewRestoreAllowed = Vue.ref(true)
  const previewRaw = Vue.ref<unknown>(null)
  const previewData = Vue.reactive({
    info: [] as { key: string; value: string }[],
    account: [] as { key: string; value: string }[],
    tasks: [] as { app_id: string; app_name: string; enabled: boolean }[],
    instances: [] as unknown[],
  })
  const blockedRestoreTimes = Vue.ref(new Set<string>())
  const t = (key: string) => key

  const factory = new Function(
    'props',
    'restoreTarget',
    'previewOpen',
    'previewLoading',
    'previewError',
    'previewTime',
    'previewItem',
    'previewWarnings',
    'previewRestoreAllowed',
    'previewRaw',
    'previewData',
    'blockedRestoreTimes',
    't',
    `${callbackJavaScript}
return handlePreview;`
  ) as (...args: unknown[]) => (item: { time: string }) => Promise<void>

  const handlePreview = factory(
    props,
    restoreTarget,
    previewOpen,
    previewLoading,
    previewError,
    previewTime,
    previewItem,
    previewWarnings,
    previewRestoreAllowed,
    previewRaw,
    previewData,
    blockedRestoreTimes,
    t
  )
  return {
    handlePreview,
    previewOpen,
    previewLoading,
    previewError,
    previewWarnings,
    previewRestoreAllowed,
    previewRaw,
    previewData,
    blockedRestoreTimes,
  }
}

describe('ConfigRestoreSection preview state', () => {
  it('keeps raw files previewable while blocking an unrestorable payload', async () => {
    const payload = {
      code: 200,
      data: {
        info: [],
        account: [],
        tasks: [],
        instances: [{ idx: 1 }],
        files: [{ path: '1/game_account.yml', size: 5 }],
        warnings: ['账号配置损坏'],
        restoreAllowed: false,
      },
    }
    const runtime = createRuntime(async () => payload)
    const item = { time: '20261002-160000' }

    await runtime.handlePreview(item)

    expect(runtime.previewData.instances).toEqual([{ idx: 1 }])
    expect(runtime.previewWarnings.value).toEqual(['账号配置损坏'])
    expect(runtime.previewRestoreAllowed.value).toBe(false)
    expect(runtime.blockedRestoreTimes.value.has(item.time)).toBe(true)
    expect(runtime.previewRaw.value).toEqual(payload.data)
    expect(runtime.previewError.value).toBe('')
  })

  it('blocks restore when preview request itself fails', async () => {
    const runtime = createRuntime(async () => {
      throw new Error('preview unavailable')
    })
    const item = { time: '20261002-160001' }

    await runtime.handlePreview(item)

    expect(runtime.previewError.value).toBe('preview unavailable')
    // 请求失败≠备份损坏：不进「内容不完整」警示，只锁恢复并展示错误
    expect(runtime.previewWarnings.value).toEqual([])
    expect(runtime.previewRestoreAllowed.value).toBe(false)
    expect(runtime.blockedRestoreTimes.value.has(item.time)).toBe(true)
    expect(runtime.previewRaw.value).toBeNull()
  })

  it('keeps normal top-level responses compatible', async () => {
    const apiPreview = vi.fn(async () => ({
      code: 200,
      info: [{ key: 'name', value: 'backup' }],
      account: [],
      tasks: [],
      instances: [],
    }))
    const runtime = createRuntime(apiPreview)
    const item = { time: '20261002-160002' }

    await runtime.handlePreview(item)

    expect(apiPreview).toHaveBeenCalledTimes(1)
    expect(runtime.previewData.info).toEqual([{ key: 'name', value: 'backup' }])
    expect(runtime.previewWarnings.value).toEqual([])
    expect(runtime.previewRestoreAllowed.value).toBe(true)
    expect(runtime.blockedRestoreTimes.value.has(item.time)).toBe(false)
  })

  it('allows restore after a failed preview succeeds on retry', async () => {
    const preview = vi
      .fn<() => Promise<PreviewPayload>>()
      .mockRejectedValueOnce(new Error('preview unavailable'))
      .mockResolvedValueOnce({ code: 200, data: { restoreAllowed: true, warnings: [] } })
    const runtime = createRuntime(preview)
    const item = { time: '20261002-160003' }

    await runtime.handlePreview(item)
    expect(runtime.blockedRestoreTimes.value.has(item.time)).toBe(true)

    await runtime.handlePreview(item)
    expect(runtime.previewError.value).toBe('')
    expect(runtime.previewRestoreAllowed.value).toBe(true)
    expect(runtime.blockedRestoreTimes.value.has(item.time)).toBe(false)
  })
})
