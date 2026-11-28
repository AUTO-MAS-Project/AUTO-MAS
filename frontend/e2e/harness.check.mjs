import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { parse as parseToml } from 'smol-toml'
import { parse, stringify } from 'yaml'
import { cleanupRealRun } from './real-cleanup.ts'
import { acquireRealRunLock, seedBrowserProfile, seedRealProfile } from './run.mjs'

test('真实任务响应缺失时先找回并终止任务，空闲未确认时不关闭模拟器', async () => {
  const calls = []
  const cleanup = {
    startAttempted: true,
    taskId: undefined,
    findTask: async () => {
      calls.push('find')
      return 'accepted-task'
    },
    terminateTask: async taskId => {
      calls.push(`stop:${taskId}`)
    },
    waitForIdle: async () => {
      calls.push('idle')
    },
    closeEmulator: async () => {
      calls.push('close')
    },
  }
  await cleanupRealRun(cleanup)
  assert.deepEqual(calls, ['find', 'stop:accepted-task', 'idle', 'close'])
  calls.length = 0
  await assert.rejects(
    cleanupRealRun({
      ...cleanup,
      waitForIdle: async () => {
        throw new Error('busy')
      },
    }),
    /busy/
  )
  assert.deepEqual(calls, ['find', 'stop:accepted-task'])
  calls.length = 0
  await assert.rejects(
    cleanupRealRun({ ...cleanup, findTask: async () => undefined }),
    /无法确认任务/
  )
  assert.deepEqual(calls, [])
})

test('插件与历史种子只写普通隔离根，真实与就地模式保持原数据', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-history-check-'))
  try {
    await seedBrowserProfile(root, { real: true, inPlace: false })
    await seedBrowserProfile(root, { real: false, inPlace: true })
    assert.deepEqual(await readdir(root), [])
    const fixtureEnv = await seedBrowserProfile(root, { real: false, inPlace: false })
    assert.ok((await readFile(path.join(root, 'data', 'history.db'))).length > 0)
    assert.ok((await readdir(path.join(root, 'history'))).length > 0)
    const pluginRegistry = parse(
      await readFile(path.join(root, 'config', 'plugin_registry.yaml'), 'utf8')
    )
    const enabledPlugins = Object.values(pluginRegistry.data)
      .map(({ info }) => info)
      .filter(({ enabled }) => enabled)
    for (const name of ['maa_adapter', 'whimbox_adapter']) {
      assert.ok(enabledPlugins.some(({ plugin_name }) => plugin_name === name))
    }
    const maaEnd = enabledPlugins.find(({ plugin_name }) => plugin_name === 'maaend_adapter')
    assert.equal(fixtureEnv.AUTO_MAS_E2E_MAAEND_READY, maaEnd ? '1' : '0')
    if (process.env.AUTO_MAS_E2E_MAAEND_WHEEL?.trim()) {
      assert.equal(maaEnd?.source, 'installed')
    }
    const sourceRoot = process.env.AUTO_MAS_E2E_PLUGIN_PROJECTS?.trim()
    if (sourceRoot) {
      const entries = await readdir(sourceRoot, { withFileTypes: true })
      const projects = entries.some(entry => entry.name === 'pyproject.toml')
        ? [sourceRoot]
        : entries
            .filter(entry => entry.isDirectory() || entry.isSymbolicLink())
            .map(entry => path.join(sourceRoot, entry.name))
      for (const project of projects) {
        let declaration
        try {
          declaration = await readFile(path.join(project, 'pyproject.toml'), 'utf8')
        } catch (error) {
          if (error.code !== 'ENOENT') throw error
          continue
        }
        const keywords = parseToml(declaration).project?.keywords ?? []
        const id = keywords.find(keyword => keyword.startsWith('auto-mas-id:'))
        const name = id?.slice('auto-mas-id:'.length)
        if (
          [
            'maaend_adapter',
            'mumu_adapter',
            'ldplayer_adapter',
            'mod_avd_adapter',
            'general_emulator_adapter',
            'win_process_adapter',
          ].includes(name)
        ) {
          assert.ok(
            enabledPlugins.some(plugin => plugin.plugin_name === name && plugin.source === 'local'),
            `${name} 应从提供的源码启用`
          )
        }
      }
    }
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('真实流程按公开 MAS 配置隔离用户并允许无模拟器专项', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-check-'))
  const source = path.join(root, 'source')
  const target = path.join(root, 'target')
  const scriptId = '00000000-0000-0000-0000-000000000001'
  const userId = '00000000-0000-0000-0000-000000000002'
  const emulatorId = '00000000-0000-0000-0000-000000000003'
  const planId = '00000000-0000-0000-0000-000000000004'
  const collection = (id, type, value) => ({ instances: [{ uid: id, type }], [id]: value })
  const user = {
    Info: { Name: 'test account', Status: true, Password: 'opaque-ciphertext', StageMode: planId },
    Notify: { Enabled: true, ServerChanKey: 'do-not-copy' },
    SubConfigsInfo: { Notify_CustomWebhooks: { instances: [{ uid: 'secret' }] } },
  }
  const script = {
    Info: { Name: 'test script' },
    Emulator: { Id: emulatorId, Index: '0' },
    SubConfigsInfo: { UserData: collection(userId, 'MaaUserConfig', user) },
  }
  const scripts = collection(scriptId, 'MaaConfig', script)
  scripts.instances.push({ uid: 'unselected', type: 'MaaConfig' })
  scripts.unselected = { private: 'do-not-copy' }
  const config = path.join(source, 'config')
  const env = Object.fromEntries(
    Object.entries({
      EMULATOR_ID: emulatorId,
      EMULATOR_INDEX: '0',
      SCRIPT_ID: scriptId,
      USER_ID: userId,
      ACCOUNT_NAME: 'test account',
    }).map(([key, value]) => [`AUTO_MAS_E2E_${key}`, value])
  )
  env.AUTO_MAS_E2E_EMULATOR_ID = emulatorId
  try {
    await mkdir(config, { recursive: true })
    for (const [name, value] of Object.entries({
      ScriptConfig: scripts,
      EmulatorConfig: collection(emulatorId, 'EmulatorConfig', { Info: {} }),
      PlanConfig: collection(planId, 'MaaPlanConfig', { plan: 'selected' }),
      QueueConfig: { startup: 'do-not-copy' },
      Config: { credentials: 'do-not-copy' },
    }))
      await writeFile(path.join(config, `${name}.json`), JSON.stringify(value))
    const profile = path.join('data', scriptId, 'Default', 'ConfigFile')
    await mkdir(path.join(source, profile), { recursive: true })
    await writeFile(path.join(source, profile, 'opaque.json'), 'opaque upstream content')
    await writeFile(path.join(source, 'data', scriptId, 'Temp.ready'), 'do-not-copy')

    await seedRealProfile(source, target, env)
    const seeded = JSON.parse(await readFile(path.join(target, 'config', 'ScriptConfig.json')))
    assert.deepEqual(seeded.instances, [{ uid: scriptId, type: 'MaaConfig' }])
    const account = seeded[scriptId].SubConfigsInfo.UserData[userId]
    assert.equal(account.Info.Password, 'opaque-ciphertext')
    assert.equal(account.Notify, undefined)
    assert.equal(account.SubConfigsInfo.Notify_CustomWebhooks, undefined)
    assert.deepEqual((await readdir(path.join(target, 'config'))).sort(), [
      'EmulatorConfig.json',
      'PlanConfig.json',
      'ScriptConfig.json',
    ])
    assert.equal(
      await readFile(path.join(target, profile, 'opaque.json'), 'utf8'),
      'opaque upstream content'
    )
    await assert.rejects(readFile(path.join(target, 'data', scriptId, 'Temp.ready')))
    assert.equal(
      await readFile(path.join(config, 'ScriptConfig.json'), 'utf8'),
      JSON.stringify(scripts)
    )
    await assert.rejects(
      seedRealProfile(source, target, { ...env, AUTO_MAS_E2E_SCRIPT_ID: '../outside' }),
      /UUID/
    )
    await assert.rejects(
      seedRealProfile(source, target, { ...env, AUTO_MAS_E2E_ACCOUNT_NAME: 'wrong' }),
      /用户/
    )
    await assert.rejects(
      seedRealProfile(source, target, { ...env, AUTO_MAS_E2E_EMULATOR_INDEX: '1' }),
      /模拟器/
    )

    const makeId = serial => `00000000-0000-0000-0000-${String(serial).padStart(12, '0')}`
    for (const { scriptType, userType, planField, planType, serial } of [
      {
        scriptType: 'MaaEndConfig',
        userType: 'MaaEndUserConfig',
        planField: 'SanityMode',
        planType: 'MaaEndPlanConfig',
        serial: 101,
      },
      {
        scriptType: 'MSSConfig',
        userType: 'MSSUserConfig',
        planField: 'PlanMode',
        planType: 'MSSPlanConfig',
        serial: 107,
      },
      {
        scriptType: 'OkNteConfig',
        userType: 'OkNteUserConfig',
        planField: 'PlanMode',
        planType: 'OkNtePlanConfig',
        serial: 119,
      },
      {
        scriptType: 'M9AConfig',
        userType: 'M9AUserConfig',
        planField: undefined,
        planType: undefined,
        serial: 110,
      },
      {
        scriptType: 'MaaFWConfig',
        userType: 'MaaFWUserConfig',
        planField: undefined,
        planType: undefined,
        serial: 116,
      },
    ]) {
      const variantScriptId = makeId(serial)
      const variantUserId = makeId(serial + 1)
      const variantPlanId = planType ? makeId(serial + 2) : undefined
      const info = {
        Name: `${scriptType} account`,
        Status: true,
        ...(planField && variantPlanId ? { [planField]: variantPlanId } : {}),
        ...(scriptType === 'MaaEndConfig' ? { AutoEssenceMode: 'Native' } : {}),
      }
      const variantScript = collection(variantScriptId, scriptType, {
        Info: { Name: `${scriptType} script` },
        SubConfigsInfo: {
          UserData: collection(variantUserId, userType, { Info: info }),
        },
      })
      await writeFile(path.join(config, 'ScriptConfig.json'), JSON.stringify(variantScript))
      if (planType && variantPlanId) {
        await writeFile(
          path.join(config, 'PlanConfig.json'),
          JSON.stringify(collection(variantPlanId, planType, { plan: 'selected' }))
        )
      }
      if (['MaaFWConfig', 'M9AConfig', 'MSSConfig'].includes(scriptType)) {
        const view = path.join(
          source,
          'data',
          'mfw',
          variantScriptId.replaceAll('-', '').slice(0, 12)
        )
        await mkdir(view, { recursive: true })
        await writeFile(path.join(view, 'interface.json'), '{"name":"opaque project"}')
        await writeFile(path.join(view, 'agent.txt'), 'selected MFW view')
      }

      if (scriptType === 'OkNteConfig') {
        const quick = path.join(source, 'data', variantScriptId, variantUserId, 'QuickConfig')
        await mkdir(quick, { recursive: true })
        await writeFile(path.join(quick, 'daily.json'), 'opaque account quick configuration')
      }
      const variantTarget = path.join(root, `${scriptType}-target`)
      await seedRealProfile(source, variantTarget, {
        AUTO_MAS_E2E_SCRIPT_ID: variantScriptId,
        AUTO_MAS_E2E_USER_ID: variantUserId,
        AUTO_MAS_E2E_ACCOUNT_NAME: `${scriptType} account`,
      })
      const variantSeed = JSON.parse(
        await readFile(path.join(variantTarget, 'config', 'ScriptConfig.json'))
      )
      assert.deepEqual(variantSeed.instances, [{ uid: variantScriptId, type: scriptType }])
      if (scriptType === 'OkNteConfig') {
        assert.equal(
          await readFile(
            path.join(
              variantTarget,
              'data',
              variantScriptId,
              variantUserId,
              'QuickConfig',
              'daily.json'
            ),
            'utf8'
          ),
          'opaque account quick configuration'
        )
      }
      if (planType && variantPlanId) {
        const selectedPlan = JSON.parse(
          await readFile(path.join(variantTarget, 'config', 'PlanConfig.json'))
        )
        assert.deepEqual(selectedPlan.instances, [{ uid: variantPlanId, type: planType }])
      } else {
        await assert.rejects(readFile(path.join(variantTarget, 'config', 'PlanConfig.json')), {
          code: 'ENOENT',
        })
      }
      if (['MaaFWConfig', 'M9AConfig', 'MSSConfig'].includes(scriptType)) {
        assert.equal(
          await readFile(
            path.join(
              variantTarget,
              'data',
              'mfw',
              variantScriptId.replaceAll('-', '').slice(0, 12),
              'agent.txt'
            ),
            'utf8'
          ),
          'selected MFW view'
        )
      }
    }

    const hsrId = makeId(113)
    const hsrUserId = makeId(114)
    const hsrOtherUserId = makeId(115)
    const hsrScript = collection(hsrId, 'HSRConfig', {
      Info: { Name: 'HSR cloud script' },
      Game: { Platform: 'Cloud' },
      SubConfigsInfo: {
        UserData: collection(hsrUserId, 'HSRUserConfig', {
          Info: { Name: 'HSR cloud account', Status: true },
        }),
      },
    })
    hsrScript[hsrId].SubConfigsInfo.UserData.instances.push({
      uid: hsrOtherUserId,
      type: 'HSRUserConfig',
    })
    hsrScript[hsrId].SubConfigsInfo.UserData[hsrOtherUserId] = {
      Info: { Name: 'unselected HSR account', Status: true },
    }
    await writeFile(path.join(config, 'ScriptConfig.json'), JSON.stringify(hsrScript))
    await mkdir(path.join(source, 'data', hsrId, hsrUserId, 'cloud-profile'), {
      recursive: true,
    })
    await writeFile(
      path.join(source, 'data', hsrId, hsrUserId, 'cloud-profile', 'Cookies'),
      'opaque cloud session'
    )
    await mkdir(path.join(source, 'data', hsrId, hsrOtherUserId, 'cloud-profile'), {
      recursive: true,
    })
    await writeFile(
      path.join(source, 'data', hsrId, hsrOtherUserId, 'cloud-profile', 'Cookies'),
      'do-not-copy'
    )
    const hsrTarget = path.join(root, 'HSRConfig-target')
    await seedRealProfile(source, hsrTarget, {
      AUTO_MAS_E2E_SCRIPT_ID: hsrId,
      AUTO_MAS_E2E_USER_ID: hsrUserId,
      AUTO_MAS_E2E_ACCOUNT_NAME: 'HSR cloud account',
    })
    assert.equal(
      await readFile(
        path.join(hsrTarget, 'data', hsrId, hsrUserId, 'cloud-profile', 'Cookies'),
        'utf8'
      ),
      'opaque cloud session'
    )
    await assert.rejects(
      readFile(path.join(hsrTarget, 'data', hsrId, hsrOtherUserId, 'cloud-profile', 'Cookies')),
      { code: 'ENOENT' }
    )

    await writeFile(
      path.join(config, 'ScriptConfig.json'),
      JSON.stringify(collection('00000000-0000-0000-0000-000000000007', 'NewConfig', {}))
    )
    await assert.rejects(
      seedRealProfile(source, target, {
        ...env,
        AUTO_MAS_E2E_SCRIPT_ID: '00000000-0000-0000-0000-000000000007',
      }),
      /尚未登记专项类型/
    )

    const betterGiId = '00000000-0000-0000-0000-000000000005'
    const betterGiUserId = '00000000-0000-0000-0000-000000000006'
    const betterGi = collection(betterGiId, 'BetterGIConfig', {
      Info: { Name: 'BetterGI test script' },
      SubConfigsInfo: {
        UserData: collection(betterGiUserId, 'BetterGIUserConfig', {
          Info: { Name: 'BetterGI test account', Status: true },
        }),
      },
    })
    await writeFile(path.join(config, 'ScriptConfig.json'), JSON.stringify(betterGi))
    for (const directory of ['ConfigFile', 'Infrastructure']) {
      const legacyPath = path.join(source, 'data', betterGiId, betterGiUserId, directory)
      await mkdir(legacyPath, { recursive: true })
      await writeFile(path.join(legacyPath, 'legacy.json'), 'not-needed')
    }
    for (const [directory, filename, content] of [
      ['OneDragon', 'profile.json', '{"opaque":"one-dragon"}'],
      ['ScriptGroup', 'group.json', '{"opaque":"script-group"}'],
      ['GlobalDomain', 'settings.json', '{"opaque":"domain"}'],
      ['GlobalStygian', 'settings.json', '{"opaque":"stygian"}'],
      ['Temp', 'runtime.json', 'do-not-copy'],
      ['BetterGIBackups', 'snapshot.json', 'do-not-copy'],
    ]) {
      const directoryPath = path.join(source, 'data', betterGiId, betterGiUserId, directory)
      await mkdir(directoryPath, { recursive: true })
      await writeFile(path.join(directoryPath, filename), content)
    }
    const betterGiEnv = {
      AUTO_MAS_E2E_SCRIPT_ID: betterGiId,
      AUTO_MAS_E2E_USER_ID: betterGiUserId,
      AUTO_MAS_E2E_ACCOUNT_NAME: 'BetterGI test account',
    }
    const betterGiTarget = path.join(root, 'bettergi-target')
    await seedRealProfile(source, betterGiTarget, betterGiEnv)
    const betterGiSeed = JSON.parse(
      await readFile(path.join(betterGiTarget, 'config', 'ScriptConfig.json'))
    )
    assert.equal(betterGiSeed[betterGiId].Info.Name, 'BetterGI test script')
    assert.deepEqual(betterGiSeed[betterGiId].SubConfigsInfo.UserData.instances, [
      { uid: betterGiUserId, type: 'BetterGIUserConfig' },
    ])
    assert.deepEqual((await readdir(path.join(betterGiTarget, 'config'))).sort(), [
      'ScriptConfig.json',
    ])
    for (const directory of ['ConfigFile', 'Infrastructure']) {
      assert.equal(
        await readFile(
          path.join(betterGiTarget, 'data', betterGiId, betterGiUserId, directory, 'legacy.json'),
          'utf8'
        ),
        'not-needed'
      )
    }
    for (const [directory, filename, content] of [
      ['OneDragon', 'profile.json', '{"opaque":"one-dragon"}'],
      ['ScriptGroup', 'group.json', '{"opaque":"script-group"}'],
      ['GlobalDomain', 'settings.json', '{"opaque":"domain"}'],
      ['GlobalStygian', 'settings.json', '{"opaque":"stygian"}'],
    ]) {
      assert.equal(
        await readFile(
          path.join(betterGiTarget, 'data', betterGiId, betterGiUserId, directory, filename),
          'utf8'
        ),
        content
      )
    }
    for (const directory of ['Temp', 'BetterGIBackups']) {
      await assert.rejects(
        readdir(path.join(betterGiTarget, 'data', betterGiId, betterGiUserId, directory))
      )
    }
  } finally {
    assert.equal(path.dirname(root), path.resolve(tmpdir()))
    await rm(root, { recursive: true, force: true })
  }
})

test('真实入口拒绝并发运行', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-lock-'))
  const lockPath = path.join(root, 'real.lock')
  try {
    const release = await acquireRealRunLock(lockPath)
    await assert.rejects(acquireRealRunLock(lockPath), /已有本机真实 E2E/)
    await release()
    const releaseAfterCleanup = await acquireRealRunLock(lockPath)
    await releaseAfterCleanup()
  } finally {
    assert.equal(path.dirname(root), path.resolve(tmpdir()))
    await rm(root, { recursive: true, force: true })
  }
})

test('真实流程无需环境变量即可选中本机第一个已启用用户', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-pick-'))
  const source = path.join(root, 'source')
  const config = path.join(source, 'config')
  const collection = (id, type, value) => ({ instances: [{ uid: id, type }], [id]: value })
  const disabledScriptId = '00000000-0000-0000-0000-000000000011'
  const enabledScriptId = '00000000-0000-0000-0000-000000000012'
  const enabledUserId = '00000000-0000-0000-0000-000000000013'
  try {
    await mkdir(config, { recursive: true })
    const scripts = {
      instances: [
        { uid: disabledScriptId, type: 'MaaConfig' },
        { uid: enabledScriptId, type: 'GeneralConfig' },
      ],
      [disabledScriptId]: {
        Info: { Name: 'disabled script' },
        SubConfigsInfo: {
          UserData: collection('00000000-0000-0000-0000-000000000014', 'GeneralUserConfig', {
            Info: { Name: 'disabled account', Status: false },
          }),
        },
      },
      [enabledScriptId]: {
        Info: { Name: 'enabled script' },
        SubConfigsInfo: {
          UserData: collection(enabledUserId, 'GeneralUserConfig', {
            Info: { Name: '本机账号', Status: true },
          }),
        },
      },
    }
    await writeFile(path.join(config, 'ScriptConfig.json'), JSON.stringify(scripts))

    const selected = await seedRealProfile(source, path.join(root, 'target'), {})
    assert.equal(selected.scriptId, enabledScriptId)
    assert.equal(selected.userId, enabledUserId)
    assert.equal(selected.accountName, '本机账号')

    // 显式指定一个不存在的目标时给出可读错误，而不是静默换一个用户
    await assert.rejects(
      seedRealProfile(source, path.join(root, 'target'), {
        AUTO_MAS_E2E_ACCOUNT_NAME: '不存在的账号',
      }),
      /匹配/
    )
    await writeFile(
      path.join(config, 'ScriptConfig.json'),
      JSON.stringify({ instances: [], [enabledScriptId]: '' })
    )
    await assert.rejects(
      seedRealProfile(source, path.join(root, 'target'), { AUTO_MAS_E2E_ACCOUNT_NAME: '任意' }),
      /已启用/
    )
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('MAA 现行格式把 StageMode 放在 Stage 组时也复制计划表', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-stage-'))
  const source = path.join(root, 'source')
  const target = path.join(root, 'target')
  const scriptId = '00000000-0000-0000-0000-000000000021'
  const userId = '00000000-0000-0000-0000-000000000022'
  const planId = '00000000-0000-0000-0000-000000000023'
  const collection = (id, type, value) => ({ instances: [{ uid: id, type }], [id]: value })
  try {
    await mkdir(path.join(source, 'config'), { recursive: true })
    for (const [name, value] of Object.entries({
      ScriptConfig: collection(scriptId, 'MaaConfig', {
        Info: { Name: 'test script' },
        SubConfigsInfo: {
          UserData: collection(userId, 'MaaUserConfig', {
            Info: { Name: 'test account', Status: true },
            Stage: { StageMode: planId },
          }),
        },
      }),
      PlanConfig: collection(planId, 'MaaPlanConfig', { plan: 'stage-mode' }),
    }))
      await writeFile(path.join(source, 'config', `${name}.json`), JSON.stringify(value))

    await seedRealProfile(source, target, {})
    const plans = JSON.parse(await readFile(path.join(target, 'config', 'PlanConfig.json')))
    assert.deepEqual(plans.instances, [{ uid: planId, type: 'MaaPlanConfig' }])
    assert.deepEqual(plans[planId], { plan: 'stage-mode' })
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

for (const { label, yaml, group, field } of [
  { label: '现行 YAML users', yaml: true, group: null, field: 'users' },
  { label: '历史 YAML UserData', yaml: true, group: null, field: 'UserData' },
  {
    label: '历史 JSON SubConfigsInfo.UserData',
    yaml: false,
    group: 'SubConfigsInfo',
    field: 'UserData',
  },
]) {
  test(`MaaEnd 真实入口按 ${label} 裁剪账号并保留两种计划引用`, async () => {
    const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-maaend-'))
    const source = path.join(root, 'source')
    const target = path.join(root, 'target')
    const config = path.join(source, 'config')
    const scriptId = '00000000-0000-0000-0000-000000000031'
    const userId = '00000000-0000-0000-0000-000000000032'
    const otherUserId = '00000000-0000-0000-0000-000000000033'
    const sanityPlanId = '00000000-0000-0000-0000-000000000034'
    const essencePlanId = '00000000-0000-0000-0000-000000000035'
    const otherPlanId = '00000000-0000-0000-0000-000000000036'
    const webhookId = '00000000-0000-0000-0000-000000000037'
    const scriptFile = yaml ? 'scripts.yaml' : 'ScriptConfig.json'
    const planFile = yaml ? 'plans.yaml' : 'PlanConfig.json'
    const serialize = yaml ? stringify : JSON.stringify
    const deserialize = yaml ? parse : JSON.parse
    const collection = (type, members) => {
      const order = Object.keys(members).map(uid => ({ uid, type }))
      return yaml ? { order, data: members } : { instances: order, ...members }
    }
    const info = {
      Name: 'isolated MaaEnd test account',
      Status: true,
      Password: 'opaque-ciphertext',
      SanityMode: sanityPlanId,
      AutoEssenceMode: essencePlanId,
    }
    const other = { Info: { Name: 'unselected account', Status: true, Password: 'unselected' } }
    const hooks = collection('Webhook', {
      [webhookId]: { Info: { Name: 'test only' }, Data: { Url: 'http://127.0.0.1:1' } },
    })
    const users = collection('MaaEndUserConfig', {
      [userId]: {
        Info: info,
        Notify: { Enabled: true, ServerChanKey: 'do-not-copy' },
        ...(yaml
          ? { Notify_CustomWebhooks: hooks }
          : { SubConfigsInfo: { Notify_CustomWebhooks: hooks } }),
      },
      [otherUserId]: other,
    })
    const script = group ? { [group]: { [field]: users } } : { [field]: users }
    if (field === 'users') {
      // 双字段时只复制新字段中的目标，不能把旧字段里的账号和密码带入隔离根。
      script.UserData = collection('MaaEndUserConfig', { [otherUserId]: other })
    }
    const original = serialize(collection('MaaEndConfig', { [scriptId]: script }))
    const plans = {
      [essencePlanId]: { Info: { Name: 'essence plan' } },
      [otherPlanId]: { Info: { Name: 'unused plan' } },
      [sanityPlanId]: { Info: { Name: 'sanity plan' } },
    }
    try {
      await mkdir(config, { recursive: true })
      await writeFile(path.join(config, scriptFile), original)
      await writeFile(path.join(config, planFile), serialize(collection('MaaEndPlanConfig', plans)))

      const selected = await seedRealProfile(source, target, {})
      assert.equal(selected.userId, userId)
      const targetConfig = path.join(target, 'config')
      assert.deepEqual((await readdir(targetConfig)).sort(), [scriptFile, planFile].sort())
      const scripts = deserialize(await readFile(path.join(targetConfig, scriptFile), 'utf8'))
      const savedScript = (scripts.data ?? scripts)[scriptId]
      const savedUsers = (group ? savedScript[group] : savedScript)[field]
      assert.deepEqual(
        savedUsers,
        collection('MaaEndUserConfig', {
          [userId]: yaml ? { Info: info } : { Info: info, SubConfigsInfo: {} },
        })
      )
      if (field === 'users') assert.equal(savedScript.UserData, undefined)
      const selectedPlans = deserialize(await readFile(path.join(targetConfig, planFile), 'utf8'))
      assert.deepEqual(
        selectedPlans,
        collection('MaaEndPlanConfig', {
          [essencePlanId]: plans[essencePlanId],
          [sanityPlanId]: plans[sanityPlanId],
        })
      )
      assert.equal(await readFile(path.join(config, scriptFile), 'utf8'), original)
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })
}
