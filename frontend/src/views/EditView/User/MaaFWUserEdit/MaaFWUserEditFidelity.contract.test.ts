import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const readSource = (name: string) =>
  readFileSync(new URL(`./${name}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

describe('MaaFW 用户配置 v6 保真契约', () => {
  const pageSource = readFileSync(new URL('../MaaFWUserEdit.vue', import.meta.url), 'utf8').replace(
    /\r\n/g,
    '\n'
  )
  const basicSource = readSource('BasicInfoSection.vue')
  const notifySource = readSource('NotifyConfigSection.vue')
  const headerSource = readSource('MaaFWUserEditHeader.vue')

  it('保留普通 MaaFW 的任务队列、扩展脚本与通知配置能力', () => {
    expect(pageSource).toContain('<TaskQueueSection')
    expect(pageSource).toContain('<ExtraScriptSection')
    expect(pageSource).toContain('<NotifyConfigSection')
    expect(pageSource).toContain('@task-option-update="handleTaskOptionUpdate"')
    expect(pageSource).toContain('@apply-preset-template="applyPresetTemplate"')
  })

  it('移除外层大卡并使用单层磨砂分区', () => {
    expect(pageSource).toContain('<a-spin :spinning="loading" class="config-shell">')
    expect(pageSource).not.toContain('<a-card class="config-card"')
    expect(pageSource).toContain('background: var(--v6-vibrancy-content)')
    expect(pageSource).toContain('border-radius: var(--v6-radius-card)')
    expect(headerSource).toContain('<PageHeader')
  })

  it('密码使用独立草稿且只能明确替换或清空', () => {
    expect(basicSource).toContain(':value="passwordDraft"')
    expect(basicSource).not.toContain('v-model:value="formData.Info.Password"')
    expect(basicSource).toContain('保存新值')
    expect(basicSource).toContain('清空原值')
    expect(basicSource).toContain("emit('sensitiveSave', 'Info.Password', 'replace'")
    expect(basicSource).toContain("emit('sensitiveSave', 'Info.Password', 'clear'")
  })

  it('Server 酱密钥使用独立草稿且保存失败保留输入', () => {
    expect(notifySource).toContain(':value="serverChanKeyDraft"')
    expect(notifySource).not.toContain('v-model:value="formData.Notify.ServerChanKey"')
    expect(notifySource).toContain("emit('sensitiveSave', 'Notify.ServerChanKey', 'replace'")
    expect(notifySource).toContain("emit('sensitiveSave', 'Notify.ServerChanKey', 'clear'")
    expect(pageSource).toContain("message.error('敏感配置保存失败，输入内容已保留')")
    expect(pageSource).toContain('sensitiveDirtyMap[key] = true')
  })

  it('敏感字段写入成功后重新加载权威数据并清空本地草稿', () => {
    expect(pageSource).toContain('await registryApi.updateUser(scriptId, userId')
    expect(pageSource).toContain('await loadUserData()')
    expect(pageSource).toContain('basicInfoRef.value?.resetPasswordDraft()')
    expect(pageSource).toContain('notifyRef.value?.resetServerChanKeyDraft()')
  })
})
