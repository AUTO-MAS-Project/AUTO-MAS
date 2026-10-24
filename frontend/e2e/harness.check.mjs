import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { promisify } from 'node:util'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { selectBatchTargets } from './real-batch.mjs'
const execFileAsync = promisify(execFile)

import {
  acquireRealRunLock,
  assertFrontendDependencies,
  parseLauncherArgs,
  pickFreePort,
  seedRealProfile,
} from './run.mjs'

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
        scriptType: 'BAAHConfig',
        userType: 'BAAHUserConfig',
        planField: 'StageMode',
        planType: 'BAAHPlanConfig',
        serial: 104,
      },
      {
        scriptType: 'MSSConfig',
        userType: 'MSSUserConfig',
        planField: 'PlanMode',
        planType: 'MSSPlanConfig',
        serial: 107,
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

// 扫出 .vue 里某个组件的开标签：跳过引号里的 >，避免 @change="(v) => ..." 把标签截断。
const findOpeningTags = (text, tagName) => {
  const tags = []
  for (const match of text.matchAll(new RegExp('<' + tagName + '\\b', 'g'))) {
    let index = match.index + match[0].length
    let quote = null
    while (index < text.length) {
      const char = text[index]
      if (quote) {
        if (char === '\\') index += 1
        else if (char === quote) quote = null
      } else if (char === '"' || char === "'") quote = char
      else if (char === '>') break
      index += 1
    }
    tags.push(text.slice(match.index, index + 1))
  }
  return tags
}

const collectVueFiles = async directory => {
  const files = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name)
    if (entry.isDirectory()) files.push(...(await collectVueFiles(fullPath)))
    else if (entry.name.endsWith('.vue')) files.push(fullPath)
  }
  return files
}

// antd 4.2.6 的 a-switch 只接受 size="small" | "default"（node_modules/ant-design-vue/es/switch/index.js:16
// SwitchSizes = tuple('small','default')）。写成 size="large" 不会让开关变大，只会刷一条
// "custom validator check failed for prop size" 的 Vue 警告，还和同一表单里 large 的兄弟控件对不齐。
// 这种错误只有真打开页面才在控制台出现，静态扫一遍源码能更早发现。
// antd 4.2.6 的 a-select 只接受 value: Array | Object | String | Number
// （node_modules/ant-design-vue/es/select/index.js:23），布尔不在其中。
// 用 a-select 承载「是/否」设置时，选中项匹配不到布尔值：下拉框看起来是空的，
// 同时每次渲染刷一条 "Invalid prop: type check failed for prop value" 警告。
// 布尔设置应当用 a-switch（或 a-radio-group，语义是模式而不是开关时）。
test('布尔设置不使用 a-select 承载', async () => {
  const srcRoot = fileURLToPath(new URL('../src', import.meta.url))
  const offenders = []
  for (const file of await collectVueFiles(srcRoot)) {
    const text = await readFile(file, 'utf8')
    for (const block of text.matchAll(/<a-select\b[\s\S]*?<\/a-select>/g)) {
      if (/:value="(?:true|false)"/.test(block[0])) {
        const line = text.slice(0, block.index).split('\n').length
        offenders.push(`${path.relative(srcRoot, file)}:${line}`)
      }
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `布尔值不能作为 a-select 的选项值（选中态匹配不到），请改用 a-switch：\n${offenders.join('\n')}`
  )
})

test('a-switch 不使用它不支持的 size 取值', async () => {
  const srcRoot = fileURLToPath(new URL('../src', import.meta.url))
  const offenders = []
  for (const file of await collectVueFiles(srcRoot)) {
    const text = await readFile(file, 'utf8')
    for (const tag of findOpeningTags(text, 'a-switch')) {
      const size = tag.match(/\bsize="([^"]+)"/)
      if (size && !['small', 'default'].includes(size[1])) {
        offenders.push(`${path.relative(srcRoot, file)}: size="${size[1]}"`)
      }
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `a-switch 的 size 只支持 small/default，请去掉无效取值：\n${offenders.join('\n')}`
  )
})

test('启动器参数不透传给 playwright', () => {
  assert.deepEqual(parseLauncherArgs(['--grep', '@smoke', '--in-place']), {
    inPlace: true,
    playwrightArgs: ['--grep', '@smoke'],
  })
  assert.deepEqual(parseLauncherArgs(['--grep', '@queue']), {
    inPlace: false,
    playwrightArgs: ['--grep', '@queue'],
  })
  // 文档里的 AUTO_MAS_E2E_IN_PLACE=1 也要生效
  assert.deepEqual(parseLauncherArgs(['--grep', '@smoke'], { AUTO_MAS_E2E_IN_PLACE: '1' }), {
    inPlace: true,
    playwrightArgs: ['--grep', '@smoke'],
  })
})
test('批量模式按专项过滤目标并拒绝未配置的专项', () => {
  const candidates = [
    { scriptType: 'MaaConfig', accountName: 'a' },
    { scriptType: 'SrcConfig', accountName: 'b' },
    { scriptType: 'MaaConfig', accountName: 'c' },
  ]
  assert.deepEqual(selectBatchTargets(candidates, []), candidates)
  assert.deepEqual(
    selectBatchTargets(candidates, ['MaaConfig']).map(candidate => candidate.accountName),
    ['a', 'c']
  )
  assert.throws(() => selectBatchTargets(candidates, ['MaaEndConfig']), /没有这些专项/)
})

test('空闲端口分配拿到的是当下真能监听的端口，且前后两次不重复', async () => {
  const first = await pickFreePort()
  const second = await pickFreePort()
  assert.equal(typeof first, 'number')
  assert.ok(first > 0 && first < 65536)
  assert.notEqual(first, second)
  // 能监听才算真的空闲：只比端口号排除不了已被占用的地址
  const server = createServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(first, '127.0.0.1', resolve)
  })
  await new Promise(resolve => server.close(resolve))
})

test('依赖缺失时先说明该装什么，而不是让十几条用例一起报找不到元素', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-deps-'))
  const empty = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-deps-empty-'))
  try {
    await writeFile(
      path.join(root, 'package.json'),
      JSON.stringify({ dependencies: { 'left-pad': '1.0.0', vue: '3.0.0' } })
    )
    await assert.rejects(assertFrontendDependencies(root), /left-pad/)
    await assert.rejects(assertFrontendDependencies(root), /yarn install/)
    // 没有 package.json（比如根目录指错）时不该阻塞：那会把真正的原因盖掉
    assert.equal(await assertFrontendDependencies(empty), undefined)
  } finally {
    await rm(root, { recursive: true, force: true })
    await rm(empty, { recursive: true, force: true })
  }
})

// playwright 会把「浏览器目录」缓存到进程里，同一进程里换 PLAYWRIGHT_BROWSERS_PATH 不会生效，
// 所以两个方向各开一个子进程来验。
const runBrowserCheck = (env = {}) => {
  const runner = fileURLToPath(new URL('./run.mjs', import.meta.url))
  // Windows 上动态 import 只吃 file:// URL，直接给盘符路径会报 "Received protocol 'e:'"
  const runnerUrl = pathToFileURL(runner).href
  const code = `import(${JSON.stringify(runnerUrl)}).then(m => m.assertPlaywrightBrowser()).catch(error => { console.error(error.message); process.exit(1) })`
  return execFileAsync(process.execPath, ['-e', code], {
    env: { ...process.env, ...env },
    cwd: path.dirname(runner),
  })
}

test('浏览器没下载时说清楚要执行 yarn playwright install chromium', async () => {
  const empty = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-browsers-'))
  try {
    // 报错里那个 revision 目录名不该由我们来猜，直接真启动一次看结果
    await assert.rejects(runBrowserCheck({ PLAYWRIGHT_BROWSERS_PATH: empty }), error =>
      /yarn playwright install chromium/.test(error.stderr)
    )
  } finally {
    await rm(empty, { recursive: true, force: true })
  }
  // 浏览器装好的情况下不该报错，否则这套预检会把正常环境也拦下来。
  // CI 的格式检查 runner 不装 Playwright 浏览器（只有真正跑 e2e 的作业才装），
  // 这半段只对本地开发环境有意义。
  if (!process.env.CI) await runBrowserCheck()
})

// ── 用例目录自身的守卫 ───────────────────────────────────────────────
// 漏掉一条路由、漏掉一个标签，都不会有别的用例报警，只能在这里守。

/** 不要求进 @routes 巡检的路由，每条都必须写清原因 */
const ROUTE_SWEEP_EXEMPTIONS = new Map([
  ['/TestRouter', '仅开发模式注册的调试页，生产构建里不存在'],
  ['/OCRdev', '仅开发模式注册的调试页，生产构建里不存在'],
  ['/OverlayMaskDev', '仅开发模式注册的调试页，生产构建里不存在'],
  [
    '/settings/mystery/tokens',
    '要先解开神秘入口（访问码）才进得去，这段能力不在浏览器预览覆盖范围',
  ],
])

/**
 * 从 router/index.ts 抽出全部路由 hash。子路由写的是相对路径（mystery 下的 'tokens'），
 * 靠缩进重建父子关系拼成完整 hash，否则那条路由会永远不被巡检覆盖。
 * 带 :param 的详情页需要先造数据才进得去，由业务用例覆盖，这里只要静态路由。
 */
const collectRouterPaths = routerText => {
  const stack = []
  const paths = []
  for (const line of routerText.split('\n')) {
    const match = line.match(/^(\s*)path:\s*'([^']+)'/)
    if (!match) continue
    const indent = match[1].length
    const rawPath = match[2]
    while (stack.length > 0 && stack[stack.length - 1].indent >= indent) stack.pop()
    const parent = stack[stack.length - 1]?.full
    const full =
      rawPath.startsWith('/') || !parent ? rawPath : `${parent.replace(/\/$/, '')}/${rawPath}`
    stack.push({ indent, full })
    paths.push(full)
  }
  return paths
}

test('每条静态路由都在 @routes 巡检清单里', async () => {
  const e2eRoot = fileURLToPath(new URL('.', import.meta.url))
  const routerText = await readFile(path.join(e2eRoot, '..', 'src', 'router', 'index.ts'), 'utf8')
  const routesText = await readFile(path.join(e2eRoot, 'routes.pw.ts'), 'utf8')
  const routerPaths = collectRouterPaths(routerText)
  const swept = new Set([...routesText.matchAll(/\bpath: '([^']+)'/g)].map(match => match[1]))
  const expected = routerPaths.filter(
    routePath =>
      routePath.startsWith('/') &&
      routePath !== '/' &&
      !routePath.includes(':') &&
      !ROUTE_SWEEP_EXEMPTIONS.has(routePath)
  )
  const missing = expected.filter(routePath => !swept.has(routePath))
  const allowed = new Set([...expected, ...ROUTE_SWEEP_EXEMPTIONS.keys()])
  const stale = [...swept].filter(routePath => !allowed.has(routePath))
  const staleExemptions = [...ROUTE_SWEEP_EXEMPTIONS.keys()].filter(
    routePath => !routerPaths.includes(routePath)
  )
  assert.deepEqual(
    missing,
    [],
    `这些路由还没进 @routes 巡检（routes.pw.ts 的 ROUTE_CASES），它们白屏不会有任何用例发现：\n${missing.join('\n')}`
  )
  assert.deepEqual(
    stale,
    [],
    `这些路由登记在 @routes 里，但 router/index.ts 里已经没有对应路径了（改名或删除了？）：\n${stale.join('\n')}`
  )
  assert.deepEqual(
    staleExemptions,
    [],
    `这些路由在豁免表里，但 router/index.ts 里已经没有对应路径了，豁免该删掉：\n${staleExemptions.join('\n')}`
  )
})

test('每个用例文件都挂了标签，且标签在 README 里登记过', async () => {
  const e2eRoot = fileURLToPath(new URL('.', import.meta.url))
  const readme = await readFile(path.join(e2eRoot, 'README.md'), 'utf8')
  const tagLine = readme.split('\n').find(line => line.startsWith('标签：'))
  assert.ok(tagLine, 'README.md 里找不到以「标签：」开头的标签登记行')
  const documented = new Set([...tagLine.matchAll(/@[\w-]+/g)].map(match => match[0]))
  const specFiles = (await readdir(e2eRoot)).filter(name => name.endsWith('.pw.ts'))
  const untagged = []
  const undocumented = []
  for (const name of specFiles) {
    const text = await readFile(path.join(e2eRoot, name), 'utf8')
    // 三种写法都要认：{ tag: '@queue' } 属性、test.describe('@queue ...') 或裸 test('@mascot ...') 标题前缀
    const tags = new Set([
      ...[...text.matchAll(/\btag:\s*'(@[\w-]+)'/g)].map(match => match[1]),
      ...[...text.matchAll(/test(?:\.describe)?\(\s*[`'](@[\w-]+)/g)].map(match => match[1]),
    ])
    if (tags.size === 0) untagged.push(name)
    for (const tag of tags) {
      if (!documented.has(tag)) undocumented.push(`${name}: ${tag}`)
    }
  }
  assert.deepEqual(
    untagged,
    [],
    `这些用例文件没有标签，--grep 永远筛不到它们：\n${untagged.join('\n')}`
  )
  assert.deepEqual(
    undocumented,
    [],
    `这些标签没在 README 的「标签：」行登记，别人不知道该用哪个 --grep：\n${undocumented.join('\n')}`
  )
})

test('造数据的用例必须把造出来的数据删掉', async () => {
  const e2eRoot = fileURLToPath(new URL('.', import.meta.url))
  const specFiles = (await readdir(e2eRoot)).filter(name => name.endsWith('.pw.ts'))
  // 暂时没清理的用例文件，每条必须写清原因
  const CLEANUP_EXEMPTIONS = new Map([])
  const problems = []
  for (const name of specFiles) {
    if (CLEANUP_EXEMPTIONS.has(name)) continue
    const text = await readFile(path.join(e2eRoot, name), 'utf8')
    // 走后端接口造数据的地方，必须能在同一个文件里找到对应的删除调用。
    // 整套用例共用一个数据根，少了这一步，症状会出现在下一个断言「空状态」的文件里。
    const created = new Set([...text.matchAll(/\/api\/([\w-]+)\/add\b/g)].map(match => match[1]))
    for (const resource of created) {
      if (!text.includes(`/api/${resource}/delete`)) {
        problems.push(`${name}: 造了 ${resource} 数据但没有 /api/${resource}/delete`)
      }
    }
  }
  assert.deepEqual(
    problems,
    [],
    `这些用例留下了造出来的数据，后面断言「空状态」的用例会看到它们：\n${problems.join('\n')}`
  )
})
