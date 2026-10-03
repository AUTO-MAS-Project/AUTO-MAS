import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import { useSaveQueue } from '@/composables/useSaveQueue'

// 运行页面中的实际保存函数，在 node 环境替换 API 和反馈边界，不复制实现。
const page = readFileSync(new URL('./OkwwScriptEdit.vue', import.meta.url), 'utf8')
const script = page.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)?.[1] || ''
const names = new Set([
  'persistedLaunchType',
  'persistedRootPath',
  'persistedGamePath',
  'persistedClientPath',
  'saveField',
  'applyRootPathDefaults',
  'saveGamePath',
  'handleLaunchTypeChange',
  'saveClientPath',
])
const statements = ts.createSourceFile('page.ts', script, ts.ScriptTarget.Latest, true).statements
const functions = statements
  .filter(
    statement =>
      ts.isVariableStatement(statement) &&
      statement.declarationList.declarations.some(
        declaration => ts.isIdentifier(declaration.name) && names.has(declaration.name.text)
      )
  )
  .map(statement => statement.getText())
  .join('\n')
const body = ts.transpileModule(functions, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText

const setup = (updateScript = vi.fn().mockResolvedValue(true)) => {
  const config = {
    Info: { RootPath: 'old-root' },
    Game: { Type: 'Client', Path: 'old/launcher.exe', ClientPath: 'old-client.exe' },
  }
  const feedback = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
  const validate = vi.fn().mockResolvedValue(true)
  const refresh = vi.fn().mockResolvedValue(undefined)
  const initializing = { value: false }
  const { enqueue } = useSaveQueue()
  const methods = new Function(
    'okwwConfig',
    'isInitializing',
    'message',
    't',
    'enqueue',
    'updateScript',
    'scriptId',
    'validateGamePath',
    'refreshDerivedClientPath',
    `${body}\npersistedLaunchType = okwwConfig.Game.Type;
    persistedRootPath = okwwConfig.Info.RootPath;
    persistedGamePath = okwwConfig.Game.Path;
    persistedClientPath = okwwConfig.Game.ClientPath;
    return { applyRootPathDefaults, saveGamePath, saveClientPath, handleLaunchTypeChange };`
  )(
    config,
    initializing,
    feedback,
    (key: string) => key,
    enqueue,
    updateScript,
    'script-id',
    validate,
    refresh
  ) as {
    applyRootPathDefaults: (path: string) => Promise<boolean>
    saveGamePath: (path: string, message: string) => Promise<boolean>
    saveClientPath: (path: string) => Promise<boolean>
    handleLaunchTypeChange: (value: 'Client' | 'Launcher') => Promise<void>
  }
  return { config, feedback, validate, refresh, initializing, methods, updateScript }
}

const deferred = <T>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(settle => {
    resolve = settle
  })
  return { promise, resolve }
}

describe('OK-WW 编辑页保存', () => {
  it.each(['root', 'launcher', 'client'] as const)('保存失败回滚 %s 字段', async field => {
    const state = setup(vi.fn().mockResolvedValue(false))
    const before = structuredClone(state.config)
    const result =
      field === 'root'
        ? await state.methods.applyRootPathDefaults('new-root')
        : field === 'launcher'
          ? await state.methods.saveGamePath('new/launcher.exe', 'saved')
          : await state.methods.saveClientPath('new-client.exe')
    expect(result).toBe(false)
    expect(state.config).toEqual(before)
    expect(state.feedback.success).not.toHaveBeenCalled()
    if (field === 'launcher') expect(state.validate).toHaveBeenLastCalledWith('old/launcher.exe')
  })

  it.each(['root', 'launcher', 'client'] as const)('请求异常回滚 %s 字段', async field => {
    const state = setup(vi.fn().mockRejectedValue(new Error('offline')))
    const before = structuredClone(state.config)
    const result =
      field === 'root'
        ? state.methods.applyRootPathDefaults('new-root')
        : field === 'launcher'
          ? state.methods.saveGamePath('new/launcher.exe', 'saved')
          : state.methods.saveClientPath('new-client.exe')
    await expect(result).rejects.toThrow('offline')
    expect(state.config).toEqual(before)
  })

  it('保存成功后更新路径并刷新定位，清空手填路径恢复自动定位', async () => {
    const state = setup()
    await state.methods.saveGamePath('new\\launcher.exe', 'saved')
    expect(state.config.Game.Path).toBe('new/launcher.exe')
    await state.methods.saveClientPath('')
    expect(state.config.Game.ClientPath).toBe('')
    expect(state.refresh).toHaveBeenCalledTimes(2)
  })

  it('同字段连续保存都失败时回滚到已持久化值，不停留在中间值', async () => {
    const first = deferred<boolean>()
    const update = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce(false)
    const state = setup(update)
    const one = state.methods.saveClientPath('mid-client.exe')
    const two = state.methods.saveClientPath('new-client.exe')
    first.resolve(false)
    await Promise.all([one, two])
    expect(state.config.Game.ClientPath).toBe('old-client.exe')
    expect(update).toHaveBeenCalledTimes(2)
  })

  it.each([
    [true, true],
    [true, false],
    [false, true],
    [false, false],
  ])('快速切换前后保存结果为 %s/%s 时最终状态与落盘一致', async (firstSuccess, secondSuccess) => {
    const first = deferred<boolean>()
    let persisted = 'Client'
    const update = vi
      .fn()
      .mockImplementationOnce(async (_id, data) => {
        const success = await first.promise
        if (success) persisted = data.Game.Type
        return success
      })
      .mockImplementationOnce(async (_id, data) => {
        if (secondSuccess) persisted = data.Game.Type
        return secondSuccess
      })
    const state = setup(update)
    const one = state.methods.handleLaunchTypeChange('Launcher')
    const two = state.methods.handleLaunchTypeChange('Client')
    first.resolve(firstSuccess)
    await Promise.all([one, two])
    expect(state.config.Game.Type).toBe(persisted)
    expect(update).toHaveBeenCalledTimes(2)
    expect(state.feedback.error).toHaveBeenCalledTimes(
      Number(!firstSuccess) + Number(!secondSuccess)
    )
  })

  it('前两个请求失败，第三次切回相同目标仍会保存', async () => {
    const first = deferred<boolean>()
    const update = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true)
    const state = setup(update)
    const jobs = [
      state.methods.handleLaunchTypeChange('Launcher'),
      state.methods.handleLaunchTypeChange('Client'),
      state.methods.handleLaunchTypeChange('Launcher'),
    ]
    first.resolve(false)
    await Promise.all(jobs)
    expect(state.config.Game.Type).toBe('Launcher')
    expect(update).toHaveBeenCalledTimes(3)
  })

  it('异常请求不会阻断后续切换，回滚不会新增保存', async () => {
    const update = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(true)
    const state = setup(update)
    await Promise.all([
      state.methods.handleLaunchTypeChange('Launcher'),
      state.methods.handleLaunchTypeChange('Client'),
    ])
    expect(state.config.Game.Type).toBe('Client')
    expect(update).toHaveBeenCalledTimes(2)
    expect(state.feedback.error).toHaveBeenCalledTimes(1)
  })

  it('初始化载入不发起保存', async () => {
    const state = setup()
    state.initializing.value = true
    await state.methods.handleLaunchTypeChange('Launcher')
    expect(state.updateScript).not.toHaveBeenCalled()
  })
})
