import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { acquireRealRunLock, seedRealProfile } from './run.mjs'

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
