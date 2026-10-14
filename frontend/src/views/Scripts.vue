<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  DownOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import { TaskMode } from '@/api'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import { useMaaGuiSession } from '@/composables/useMaaGuiSession'
import DocLink from '@/components/DocLink.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { useManagedScriptsApi } from '@/composables/useManagedScriptsApi'
import { useApiQuery } from '@/composables/useApiQuery'
import { apiErrorMessage } from '@/utils/apiResult'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import ManagedScriptList from '@/views/scripts/components/ManagedScriptList.vue'
import ManagedConfigEditor from '@/views/scripts/components/ManagedConfigEditor.vue'
import type { ManagedScript, ManagedUser } from '@/views/scripts/managedScriptTypes'

const { t } = useI18n()
const api = useManagedScriptsApi()
const rows = ref<ManagedScript[]>([])
const types = ref<Array<{ name: string; display_name?: string; supported_modes?: string }>>([])
const {
  maaConfigLoading,
  showMaaConfigMask,
  stoppingMaaConfig,
  startSession,
  saveSession,
  stopSession,
} = useMaaGuiSession()
const query = ref('')
const createOpen = ref(false)
const selectedType = ref('')
const creating = ref(false)
const pending = reactive<Record<string, boolean>>({})
const editor = ref<{ scriptId: string; userId?: string } | null>(null)
const listRef = ref<InstanceType<typeof ManagedScriptList> | null>(null)
const busy = ref(false)
const editingScript = computed(
  () => rows.value.find(item => item.uid === editor.value?.scriptId) ?? null
)
const editingUser = computed(() =>
  editingScript.value?.users.find(item => item.uid === editor.value?.userId)
)
const typeLabels = computed(() =>
  Object.fromEntries(types.value.map(item => [item.name, item.display_name || item.name]))
)
const configurableTypes = computed(() =>
  types.value
    .filter(item => item.supported_modes?.split(',').includes(TaskMode.SCRIPT_CONFIG))
    .map(item => item.name)
)
const isSearching = computed(() => !!query.value.trim())

const {
  loading,
  error: loadError,
  execute: load,
} = useApiQuery(
  async () => {
    const [scripts, scriptTypes] = await Promise.all([api.getScripts(), api.getTypes()])
    const data = scripts.data ?? {}
    rows.value = (scripts.order ?? []).map(item => {
      const raw = (data[item.uid] ?? {}) as Record<string, unknown>
      const rawUsers =
        raw.users && typeof raw.users === 'object' ? (raw.users as Record<string, unknown>) : {}
      const userData =
        rawUsers.data && typeof rawUsers.data === 'object'
          ? (rawUsers.data as Record<string, unknown>)
          : {}
      const users = Array.isArray(rawUsers.order)
        ? rawUsers.order.map(order => {
            const entry = order as { uid: string; type: string }
            return {
              ...((userData[entry.uid] as Record<string, unknown>) ?? {}),
              uid: entry.uid,
              type: entry.type,
            } as ManagedUser
          })
        : []
      return {
        ...raw,
        uid: item.uid,
        type: item.type,
        info: asRecord(raw.info),
        ui: asRecord(raw.ui),
        users,
      } as ManagedScript
    })
    types.value = (scriptTypes.data ?? []) as typeof types.value
    return true
  },
  () => t('scripts.toast.loadFailed')
)

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

const filteredRows = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  if (!needle) return rows.value
  return rows.value.flatMap(script => {
    const scriptMatch = [script.info.name, script.uid, script.type].some(value =>
      String(value ?? '')
        .toLocaleLowerCase()
        .includes(needle)
    )
    if (scriptMatch) return [script]
    const users = script.users.filter(user =>
      [user.info.name, user.uid, user.info.account_id].some(value =>
        String(value ?? '')
          .toLocaleLowerCase()
          .includes(needle)
      )
    )
    return users.length ? [{ ...script, users }] : []
  })
})

const save = async (
  script: ManagedScript,
  section: string,
  field: string,
  value: unknown,
  user?: ManagedUser
) => {
  const key = `${script.uid}:${user?.uid ?? 'script'}:${section}:${field}`
  if (pending[key]) return false
  const target = user ?? script
  const sectionData = asRecord(target[section])
  const previous = sectionData[field]
  target[section] = { ...sectionData, [field]: value }
  pending[key] = true
  try {
    if (user)
      await api.updateUser({
        scriptId: script.uid,
        userId: user.uid,
        data: { [section]: { [field]: value } },
      })
    else await api.updateScript({ scriptId: script.uid, data: { [section]: { [field]: value } } })
    // 更新后重新读取声明和派生值，使选项范围、显隐与总览标签保持后端状态。
    await load()
    return true
  } catch (error) {
    target[section] = { ...asRecord(target[section]), [field]: previous }
    message.error(apiErrorMessage(error, t('emulator.toast.saveFailed')))
    return false
  } finally {
    pending[key] = false
  }
}

const openEditor = (script: ManagedScript, user?: ManagedUser) => {
  editor.value = { scriptId: script.uid, userId: user?.uid }
}
const configure = async (script: ManagedScript, user?: ManagedUser) => {
  await startSession({ scriptId: script.uid, userId: user?.uid })
}
const runUser = async (script: ManagedScript, user: ManagedUser) => {
  const key = `${script.uid}:${user.uid}:run`
  if (busy.value || pending[key]) return
  pending[key] = true
  try {
    await api.runUser(script.uid, user.uid)
    message.success(t('scripts.runUserStarted'))
  } catch (error) {
    message.error(apiErrorMessage(error, t('scripts.runUserFailed')))
  } finally {
    pending[key] = false
  }
}
const addScript = async () => {
  if (creating.value || !selectedType.value) return
  creating.value = true
  try {
    const result = await api.addScript(selectedType.value)
    createOpen.value = false
    selectedType.value = ''
    await load()
    const created = rows.value.find(item => item.uid === result.scriptId)
    if (created) openEditor(created)
  } catch (error) {
    message.error(apiErrorMessage(error, t('scripts.empty.desc')))
  } finally {
    creating.value = false
  }
}

const deleteScript = (script: ManagedScript, user?: ManagedUser) =>
  Modal.confirm({
    title: user ? t('scripts.deleteUserConfirm') : t('scripts.deleteScriptConfirm'),
    okType: 'danger',
    onOk: async () => {
      busy.value = true
      try {
        if (user) await api.deleteUser(script.uid, user.uid)
        else await api.deleteScript(script.uid)
        if (editor.value?.scriptId === script.uid && (!user || editor.value.userId === user.uid))
          editor.value = null
        await load()
      } catch (error) {
        message.error(
          apiErrorMessage(error, user ? t('scripts.deleteUser') : t('scripts.deleteScript'))
        )
        throw error
      } finally {
        busy.value = false
      }
    },
  })

const addUser = async (script: ManagedScript) => {
  const key = `add:${script.uid}`
  pending[key] = true
  try {
    await api.addUser(script.uid)
    await load()
  } catch (error) {
    message.error(apiErrorMessage(error, t('scripts.addUser')))
  } finally {
    pending[key] = false
  }
}

const toggleUser = async (script: ManagedScript, user: ManagedUser) => {
  await save(script, 'info', 'enabled', !user.info.enabled, user)
}

const reorderScripts = async (ids: string[]) => {
  busy.value = true
  try {
    await api.reorderScripts(ids)
    await load()
  } catch (error) {
    message.error(apiErrorMessage(error, t('scripts.toast.loadFailed')))
    await load()
  } finally {
    busy.value = false
  }
}
const reorderUsers = async (script: ManagedScript, ids: string[]) => {
  busy.value = true
  try {
    await api.reorderUsers(script.uid, ids)
    await load()
  } catch (error) {
    message.error(apiErrorMessage(error, t('scripts.toast.loadFailed')))
    await load()
  } finally {
    busy.value = false
  }
}

const changeType = (value: string) => {
  selectedType.value = value
}
const beginCreate = () => {
  selectedType.value = types.value.length === 1 ? types.value[0].name : ''
  createOpen.value = true
}
const collapseAll = () => listRef.value?.collapseAllUsers()
const expandAll = () => listRef.value?.expandAllUsers()

onMounted(load)
onUnmounted(() => {
  void stopSession()
})
</script>

<template>
  <main class="scripts-page">
    <div v-if="!editor" class="scripts-header">
      <div class="header-left">
        <div class="title-wrap">
          <h1 class="page-title">{{ t('scripts.title') }}</h1>
          <DocLink :url="MAS_DOC_URLS.scripts" />
        </div>
        <a-input
          v-model:value="query"
          allow-clear
          class="script-search"
          :placeholder="t('scripts.searchPlaceholder')"
          :aria-label="t('scripts.searchAria')"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
      </div>
      <div class="header-actions">
        <a-space size="middle">
          <a-tooltip :title="t('scripts.collapseAllTip')"
            ><a-button size="large" :disabled="!rows.length || isSearching" @click="collapseAll"
              ><template #icon><UpOutlined /></template>{{ t('scripts.collapseAll') }}</a-button
            ></a-tooltip
          >
          <a-tooltip :title="t('scripts.expandAllTip')"
            ><a-button size="large" :disabled="!rows.length || isSearching" @click="expandAll"
              ><template #icon><DownOutlined /></template>{{ t('scripts.expandAll') }}</a-button
            ></a-tooltip
          >
          <a-button size="large" :loading="loading" @click="load"
            ><template #icon><ReloadOutlined /></template>{{ t('scripts.refresh') }}</a-button
          >
          <a-button type="primary" size="large" @click="beginCreate"
            ><template #icon><PlusOutlined /></template>{{ t('scripts.addScript') }}</a-button
          >
        </a-space>
      </div>
    </div>

    <template v-if="editor && editingScript">
      <ManagedConfigEditor
        :script="editingScript"
        :user="editingUser"
        :pending="pending"
        :busy="busy"
        :save="save"
        :configurable="configurableTypes.includes(editingScript.type)"
        :config-loading="maaConfigLoading"
        @configure="configure(editingScript, editingUser)"
        @back="editor = null"
      />
    </template>
    <template v-else>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <a-spin v-if="loading && !rows.length" class="scripts-loading" />
      <div v-else-if="!rows.length && !loadError" class="empty-state">
        <div class="empty-image-container">
          <img src="@/assets/NoData.png" :alt="t('scripts.empty.alt')" class="empty-image" />
        </div>
        <h3 class="empty-title">{{ t('scripts.empty.title') }}</h3>
        <p class="empty-description">{{ t('scripts.empty.desc') }}</p>
      </div>
      <div v-else-if="!filteredRows.length" class="empty-state">
        <a-empty :description="t('scripts.empty.noMatch')"
          ><a-button @click="query = ''">{{ t('scripts.clearSearch') }}</a-button></a-empty
        >
      </div>
      <ManagedScriptList
        v-else
        ref="listRef"
        :scripts="filteredRows"
        :searching="isSearching"
        :busy="busy"
        :pending="pending"
        :type-labels="typeLabels"
        :configurable-types="configurableTypes"
        :config-loading="maaConfigLoading"
        @configure="configure"
        @edit="openEditor"
        @delete="deleteScript"
        @add-user="addUser"
        @run-user="runUser"
        @toggle-user="toggleUser"
        @reorder-scripts="reorderScripts"
        @reorder-users="reorderUsers"
      />
    </template>

    <a-modal
      v-model:open="createOpen"
      :title="t('scripts.addScript')"
      :ok-text="t('emulator.ok')"
      :cancel-text="t('emulator.cancel')"
      :confirm-loading="creating"
      :ok-button-props="{ disabled: !selectedType }"
      @ok="addScript"
    >
      <a-form layout="vertical"
        ><a-form-item :label="t('scripts.createType')"
          ><a-select
            :value="selectedType"
            :options="
              types.map(item => ({ value: item.name, label: item.display_name || item.name }))
            "
            :placeholder="t('scripts.createTypePlaceholder')"
            @update:value="changeType" /></a-form-item
      ></a-form>
    </a-modal>
    <GuiSessionMask
      :open="showMaaConfigMask"
      :icon="SettingOutlined"
      :title="t('scripts.mask.maaTitle')"
      :description="t('scripts.mask.maaDesc')"
    >
      <template #actions
        ><a-button type="primary" size="large" :loading="stoppingMaaConfig" @click="saveSession">{{
          t('scripts.mask.saveConfig')
        }}</a-button></template
      >
    </GuiSessionMask>
  </main>
</template>

<style scoped>
.scripts-page {
  min-width: 0;
}
.scripts-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 24px;
  padding: 0 4px;
}
.header-left {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 24px;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  white-space: nowrap;
}
.script-search {
  width: min(360px, 40vw);
}
.header-actions {
  flex-shrink: 0;
}
.empty-state {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.empty-image-container {
  margin-bottom: 16px;
}
.empty-image {
  max-width: 100%;
  height: auto;
}
.empty-title {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
}
.empty-description {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}
.scripts-loading {
  display: flex;
  min-height: 240px;
  align-items: center;
  justify-content: center;
}
@media (max-width: 1200px) {
  .scripts-header {
    align-items: stretch;
    flex-direction: column;
  }
  .header-left {
    justify-content: space-between;
  }
  .header-actions {
    margin-left: 0;
  }
}
@media (max-width: 768px) {
  .page-title {
    font-size: 24px;
  }
  .scripts-header {
    padding: 0 2px;
  }
  .header-left {
    align-items: stretch;
    flex-direction: column;
    gap: 12px;
  }
  .script-search {
    width: 100%;
  }
  .header-actions :deep(.ant-space) {
    flex-wrap: wrap;
  }
}
</style>
