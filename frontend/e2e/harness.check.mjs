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
