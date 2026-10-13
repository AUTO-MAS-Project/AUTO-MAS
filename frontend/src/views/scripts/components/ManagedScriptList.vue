<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import { DeleteOutlined, DownOutlined, EditOutlined, EllipsisOutlined, SettingOutlined, UpOutlined, UserAddOutlined } from '@ant-design/icons-vue'
import SettingToggleButton from '@/components/SettingToggleButton.vue'
import { parseStatusTagList } from '@/composables/useStatusTag'
import type { ManagedScript, ManagedUser } from '../managedScriptTypes'

const props = defineProps<{
  scripts: ManagedScript[]
  searching: boolean
  busy: boolean
  pending: Record<string, boolean>
  typeLabels: Record<string, string>
  configurableTypes: string[]
  configLoading: boolean
}>()
const emit = defineEmits<{
  edit: [script: ManagedScript, user?: ManagedUser]
  configure: [script: ManagedScript, user?: ManagedUser]
  delete: [script: ManagedScript, user?: ManagedUser]
  addUser: [script: ManagedScript]
  toggleUser: [script: ManagedScript, user: ManagedUser]
  reorderScripts: [ids: string[]]
  reorderUsers: [script: ManagedScript, ids: string[]]
}>()
const { t } = useI18n()
const localScripts = ref<ManagedScript[]>([])
watch(() => props.scripts, scripts => { localScripts.value = scripts.map(script => ({ ...script, users: [...script.users] })) }, { immediate: true })

// 沿用旧页的收起偏好；搜索临时展开，不覆盖用户记录。
const storageKey = 'scripts.collapsedScriptIds'
const readCollapsed = () => {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || '[]')
    return new Set<string>(Array.isArray(value) ? value.filter(id => typeof id === 'string') : [])
  } catch { return new Set<string>() }
}
const collapsed = ref(readCollapsed())
const isCollapsed = (uid: string) => !props.searching && collapsed.value.has(uid)
const saveCollapsed = () => {
  try { localStorage.setItem(storageKey, JSON.stringify([...collapsed.value])) } catch { /* 存储不可用时仅保留本次状态。 */ }
}
const toggleCollapsed = (uid: string) => {
  if (collapsed.value.has(uid)) collapsed.value.delete(uid)
  else collapsed.value.add(uid)
  saveCollapsed()
}
const collapseAllUsers = () => { collapsed.value = new Set(props.scripts.map(script => script.uid)); saveCollapsed() }
const expandAllUsers = () => { collapsed.value.clear(); saveCollapsed() }
defineExpose({ collapseAllUsers, expandAllUsers })

const revealed = ref(new Set<string>())
const credentialKey = (user: ManagedUser, field: string) => `${user.uid}:${field}`
const toggleCredential = (user: ManagedUser, field: string) => {
  const key = credentialKey(user, field)
  if (revealed.value.has(key)) revealed.value.delete(key)
  else revealed.value.add(key)
}
const logo = (script: ManagedScript) => script.type === 'MaaScript'
  ? new URL('../../../assets/MAA.png', import.meta.url).href
  : new URL('../../../assets/AUTO-MAS.ico', import.meta.url).href
</script>

<template>
  <draggable v-model="localScripts" item-key="uid" handle=".script-drag-handle" :animation="200"
    :disabled="searching || busy" ghost-class="drag-placeholder" class="draggable-scripts"
    @end="emit('reorderScripts', localScripts.map(script => script.uid))">
    <template #item="{ element: script }">
      <a-card class="script-card" :body-style="{ padding: '0' }">
        <div class="script-header">
          <div class="script-info">
            <span class="script-drag-handle" :aria-label="t('comp.dragReorder')" :title="t('comp.dragReorder')"><span class="script-drag-dots" aria-hidden="true" /></span>
            <div class="script-logo-container"><img :src="logo(script)" :alt="typeLabels[script.type] || script.type" class="script-logo" /></div>
            <div class="script-details">
              <h3 class="script-name">{{ script.info.name || script.type }}</h3>
              <a-tag color="blue" class="script-type">{{ typeLabels[script.type] || script.type }}</a-tag>
            </div>
          </div>
          <div class="header-actions">
            <a-button v-if="configurableTypes.includes(script.type)" type="primary" ghost :loading="configLoading" :disabled="busy" @click="emit('configure', script)"><template #icon><SettingOutlined /></template>{{ t('scripts.configureNative') }}</a-button>
            <a-button @click="emit('edit', script)"><template #icon><EditOutlined /></template>{{ t('comp.editScript') }}</a-button>
            <a-button class="action-button add-button" :loading="pending[`add:${script.uid}`]" :disabled="busy" @click="emit('addUser', script)"><template #icon><UserAddOutlined /></template>{{ t('comp.addUser') }}</a-button>
            <a-dropdown :trigger="['click']" :disabled="busy">
              <a-button class="action-button"><template #icon><EllipsisOutlined /></template>{{ t('comp.more') }}</a-button>
              <template #overlay><a-menu><a-menu-item key="delete" danger @click="emit('delete', script)"><DeleteOutlined />{{ t('comp.deleteScript') }}</a-menu-item></a-menu></template>
            </a-dropdown>
            <a-tooltip :title="isCollapsed(script.uid) ? t('comp.expandUsers') : t('comp.collapseUsers')">
              <a-button class="action-button" :disabled="searching" :aria-label="isCollapsed(script.uid) ? t('comp.expandUsers') : t('comp.collapseUsers')" :aria-expanded="!isCollapsed(script.uid)" @click="toggleCollapsed(script.uid)">
                <template #icon><DownOutlined v-if="isCollapsed(script.uid)" /><UpOutlined v-else /></template>
              </a-button>
            </a-tooltip>
          </div>
        </div>
        <div v-if="!isCollapsed(script.uid)" class="users-section">
          <draggable v-if="script.users.length" v-model="script.users" item-key="uid" handle=".user-drag-handle"
            :animation="200" :disabled="searching || busy" ghost-class="drag-placeholder"
            @end="emit('reorderUsers', script, script.users.map((user: ManagedUser) => user.uid))">
            <template #item="{ element: user }">
              <div class="user-item">
                <span class="user-drag-handle" :aria-label="t('comp.dragReorder')" :title="t('comp.dragReorder')"><span class="script-drag-dots" aria-hidden="true" /></span>
                <div class="user-info">
                  <div class="user-name-section">
                    <span class="user-name">{{ user.info.name || user.type }}</span>
                    <a-tag v-if="user.info.server" color="blue">{{ user.info.server }}</a-tag>
                    <a-button v-for="field in ['account_id', 'password'].filter(field => field in user.info)" :key="field" type="link" size="small" :aria-pressed="revealed.has(credentialKey(user, field))" @click="toggleCredential(user, field)">
                      {{ t(`scripts.field.${field}`) }}<template v-if="revealed.has(credentialKey(user, field))">: {{ user.info[field] || '-' }}</template>
                    </a-button>
                  </div>
                  <div class="user-info-tags">
                    <a-tag v-for="(tag, index) in parseStatusTagList(user.info.tags)" :key="index" :color="tag.color" :title="tag.text" class="info-tag">{{ tag.text }}</a-tag>
                  </div>
                </div>
                <div class="user-controls">
                  <SettingToggleButton v-if="'enabled' in user.info" size="small" :model-value="Boolean(user.info.enabled)" :loading="pending[`${script.uid}:${user.uid}:info:enabled`]" :disabled="busy" @change="emit('toggleUser', script, user)" />
                  <div class="user-actions">
                    <a-button size="small" class="user-action-btn" @click="emit('edit', script, user)"><template #icon><EditOutlined /></template>{{ t('comp.edit') }}</a-button>
                    <a-button size="small" class="user-action-btn" danger :disabled="busy" @click="emit('delete', script, user)"><template #icon><DeleteOutlined /></template>{{ t('comp.delete') }}</a-button>
                  </div>
                </div>
              </div>
            </template>
          </draggable>
          <div v-else class="empty-users"><a-empty :image="false" :description="t('scripts.noAccounts')" /></div>
        </div>
      </a-card>
    </template>
  </draggable>
</template>

<style scoped>
/* 沿用 ScriptTable 的脚本卡片和账号行结构，不对外层使用配置栅格。 */
.draggable-scripts { width: 100%; display: flex; flex-direction: column; gap: 16px; }
.script-card { border-radius: 16px; border: 1px solid var(--ant-color-border-secondary); background: var(--ant-color-bg-container); overflow: hidden; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }
.script-card:hover { border-color: var(--ant-color-primary); }
.script-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 20px 16px; border-bottom: 1px solid var(--ant-color-border-secondary); gap: 12px; }
.script-info { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0; }
.script-drag-handle, .user-drag-handle { width: 16px; height: 20px; display: inline-flex; align-items: center; justify-content: center; color: var(--ant-color-text-tertiary); cursor: grab; flex-shrink: 0; user-select: none; }
.script-drag-handle:active, .user-drag-handle:active { cursor: grabbing; }
.script-drag-dots { width: 10px; height: 16px; display: block; background-image: radial-gradient(currentColor 1.2px, transparent 1.2px); background-size: 5px 5px; opacity: 0.65; }
.drag-placeholder { opacity: 0; }
.script-logo-container { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; background: var(--ant-color-bg-layout); border: 1px solid var(--ant-color-border); overflow: hidden; flex-shrink: 0; }
.script-logo { width: 36px; height: 36px; object-fit: contain; }
.script-details { flex: 1; min-width: 0; }
.script-name { margin: 0 0 6px; font-size: 18px; font-weight: 600; color: var(--ant-color-text); line-height: 1.3; word-break: break-word; }
.script-type { font-size: 12px; font-weight: 500; border-radius: 6px; }
.header-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.action-button { border-radius: 8px; font-weight: 500; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }
.add-button { border-color: var(--ant-color-primary); color: var(--ant-color-primary); }
.add-button:hover { background: var(--ant-color-primary-bg); }
.user-item { display: flex; align-items: center; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--ant-color-border-secondary); min-height: 80px; }
.user-item:last-child { border-bottom: none; }
.user-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.user-name-section { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; overflow-wrap: anywhere; }
.user-name { font-size: 18px; font-weight: 600; color: var(--ant-color-text); }
.user-info-tags { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.info-tag { max-width: 120px; font-size: 11px; font-weight: 500; border-radius: 4px; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-controls { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
.user-actions { display: flex; gap: 8px; align-items: center; }
.user-action-btn { border-radius: 6px; font-weight: 500; min-width: 48px; }
.user-controls :deep(.setting-toggle-button.ant-btn-sm) { min-width: 48px; padding-inline: 7px; }
.empty-users { display: flex; align-items: center; justify-content: center; padding: 40px 20px; }
@media (max-width: 768px) {
  .script-header { padding: 16px 16px 12px; flex-direction: column; align-items: flex-start; }
  .header-actions { gap: 8px; }
  .user-item { padding: 16px; flex-wrap: wrap; }
  .user-controls { flex-wrap: wrap; margin-left: auto; gap: 8px; }
  .script-name { font-size: 16px; }
}
</style>
