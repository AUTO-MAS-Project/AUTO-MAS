import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const readSource = (filename: string) => readFileSync(new URL(filename, import.meta.url), 'utf8')

describe('user config runtime save lock', () => {
  it('fails pending saves instead of reporting success while locked', () => {
    const oknte = readSource('./OkNteUserEdit/OkNteConfigEditor.vue')
    expect(oknte).toContain('if (configLocked.value) {\n    if (!hasChanges.value) return true')
    expect(oknte).toContain("message.error(t('edit.configLocked'))")
    expect(oknte).toContain('return false\n  }\n  if (!hasChanges.value) return true')

    const bettergi = readSource('./BetterGIUserEdit.vue')
    expect(bettergi).toContain('const hasDragonGroupSettingsDirty = computed(')
    expect(bettergi).toContain('if (hasDragonGroupSettingsDirty.value) {')
    expect(bettergi).toContain(
      'if (!(await saveDragonGroupSettings(true, dragonGroupSaveSel))) return'
    )

    const zzzod = readSource('./ZzzOdUserEdit.vue')
    expect(zzzod).toContain('if (configLocked.value) {\n    message.error')
    expect(zzzod).toContain('return false\n  }\n  if (nativeInstanceIdx.value === null)')
  })

  it('rechecks deferred write paths after stale dialogs and pickers', () => {
    for (const filename of ['OkNteUserEdit.vue', 'ZzzOdUserEdit.vue']) {
      const source = readSource(`./${filename}`)
      expect(source).toContain(
        "onOk: async () => {\n        if (configLocked.value) {\n          message.error(t('edit.configLocked'))"
      )
    }

    const maa = readSource('./MAAUserEdit.vue')
    expect(maa).toContain(
      "const path = await window.electronAPI?.selectFile([\n      { name: t('edit.jsonFiles'), extensions: ['json'] },"
    )
    expect(maa.indexOf('if (path && path.length > 0)')).toBeLessThan(
      maa.indexOf("if (configLocked.value) {\n        message.error(t('edit.configLocked'))")
    )

    const zzzod = readSource('./ZzzOdUserEdit.vue')
    const saveTask = zzzod.slice(zzzod.indexOf('const saveTaskConfigField'))
    expect(saveTask).toContain(
      "if (configLocked.value) {\n    message.error(t('edit.configLocked'))\n    return false"
    )
  })

  it('keeps BetterGI pending input and local state coherent when locking wins', () => {
    const bettergi = readSource('./BetterGIUserEdit.vue')
    expect(bettergi).toContain(
      'const addModalOkButtonProps = computed(() => ({\n  disabled: configLocked.value'
    )
    expect(bettergi).toContain('const removeFromDragon = (item: ConfigGroupIdentity) => {')
    expect(bettergi).toContain(
      "if (configLocked.value) {\n    message.error(t('edit.configLocked'))\n    return\n  }"
    )

    const confirmAdd = bettergi.slice(bettergi.indexOf('const confirmAddToDragon'))
    expect(confirmAdd.indexOf('const added =')).toBeLessThan(
      confirmAdd.indexOf('addModal.items = []', confirmAdd.indexOf('const added ='))
    )

    const projects = readSource('./BettergiGroupProjectBody.vue')
    // #890 起「添加脚本」的 OK 按钮对四类可编辑项目（配置组 / 录制 / JS / 路径）都放开，
    // 判据由 kind !== 'scriptgroup' 放宽为 isScriptGroup（见该组件的计算属性）
    expect(projects).toContain(':ok-button-props="{ disabled: !isScriptGroup || configLocked }"')
    // #890 起改为箭头函数写法（返回值类型不变）
    expect(projects).toContain('const persistProjects = (): Promise<boolean> => {')
    // 该函数现为箭头函数，锁定时返回 Promise.resolve(false)
    expect(projects).toContain(
      "if (configLocked.value) {\n    message.error(t('edit.configLocked'))\n    return Promise.resolve(false)"
    )

    const saveSettings = projects.slice(projects.indexOf('const saveProjectSettings'))
    const savedIndex = saveSettings.indexOf('const saved = await persistProjects()')
    expect(savedIndex).toBeLessThan(saveSettings.indexOf('settingsModal.open = false', savedIndex))
  })
})
