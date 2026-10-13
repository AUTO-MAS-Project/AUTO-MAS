<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  DeleteOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  FullscreenOutlined,
  MinusOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  ShopOutlined,
  StopOutlined,
  SettingOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { useGameManagementApi } from '@/composables/useGameManagementApi'
import DeclarativeControl from '@/components/DeclarativeControl.vue'
import { apiErrorMessage } from '@/utils/apiResult'
import { useApiQuery } from '@/composables/useApiQuery'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { configurationFieldSpan } from '@/utils/declarativeLayout'

type Dict = Record<string, unknown>
type Hint = {
  field?: string
  component?: string
  width?: number | null
  editable?: boolean
  path_kind?: string | null
  min?: number | null
  max?: number | null
  options?: Array<{ value?: string | number | boolean; label?: string }>
}
type Entry = Dict & { uid: string; type: string; info: Dict; action: Dict; devices: Dict; ui: Dict }
type SearchRow = { uid: string; name?: string; type?: string }

const { t } = useI18n()
const api = useGameManagementApi()
const saving = ref<string | null>(null)
const deviceSaving = ref<string | null>(null)
const rows = ref<Entry[]>([])
const types = ref<Array<{ name: string; display_name?: string }>>([])
const activeKey = ref(localStorage.getItem('games_active_key') || '')
const createOpen = ref(false)
const selectedType = ref('')
const searchLoading = ref(false)
const searchRows = ref<SearchRow[]>([])

const fieldTranslations: Record<string, () => string> = {
  name: () => t('emulator.nameLabel'),
  path: () => t('emulator.pathLabel'),
  max_wait_time: () => t('emulator.waitLabel'),
  force_kill: () => t('emulator.forceCloseLabel'),
  status: () => t('emulator.colStatus'),
  index: () => t('emulator.instanceIndex'),
  adb_address: () => t('emulator.colAdb'),
  refresh: () => t('emulator.refresh'),
  create_instance: () => t('emulator.createInstance'),
}

const fieldHelp = (field: string) => {
  const key = (
    {
      name: 'emulator.fieldHelp.name',
      path: 'emulator.fieldHelp.path',
      max_wait_time: 'emulator.fieldHelp.maxWaitTime',
      force_kill: 'emulator.fieldHelp.forceKill',
    } as Record<string, string>
  )[field]
  return key ? t(key) : null
}

const actionLabel = (field: string) => {
  const key = {
    refresh: 'emulator.refresh',
    create_instance: 'emulator.createInstance',
    open: 'emulator.deviceActions.open',
    close: 'emulator.deviceActions.close',
    show: 'emulator.deviceActions.show',
    hide: 'emulator.deviceActions.hide',
    minimize: 'emulator.deviceActions.minimize',
    maximize: 'emulator.deviceActions.maximize',
    open_store: 'emulator.deviceActions.openStore',
    delete_instance: 'emulator.deviceActions.deleteInstance',
  }[field]
  return key ? t(key) : fieldLabel(field)
}

const actionIcon = (field: string) =>
  ({
    refresh: ReloadOutlined,
    create_instance: PlusOutlined,
    open: PlayCircleOutlined,
    close: StopOutlined,
    show: EyeOutlined,
    hide: EyeInvisibleOutlined,
    minimize: MinusOutlined,
    maximize: FullscreenOutlined,
    open_store: ShopOutlined,
    delete_instance: DeleteOutlined,
  })[field] || SettingOutlined

const fieldLabel = (field: string) => {
  const translated = fieldTranslations[field]?.()
  if (translated) return translated
  const key = `emulator.${field}`
  const localized = t(key)
  return localized === key
    ? field.replace(/_/g, ' ').replace(/(^|\s)\w/g, (char: string) => char.toUpperCase())
    : localized
}

const statusText = (value: unknown) => {
  const key =
    ['online', 'offline', 'starting', 'closing', 'error', 'notFound', 'unknown'][Number(value)] ??
    'unknown'
  return t(`emulator.deviceStatus.${key}`)
}

const statusColor = (value: unknown) => {
  const status = Number(value)
  if (status === 0) return 'success'
  if (status === 2) return 'processing'
  if (status === 4 || status === 5) return 'error'
  if (status === 3) return 'warning'
  return 'default'
}

const normalize = (uid: string, type: string, value: Dict): Entry => ({
  uid,
  type,
  info: value.info && typeof value.info === 'object' ? (value.info as Dict) : {},
  action: value.action && typeof value.action === 'object' ? (value.action as Dict) : {},
  devices: value.devices && typeof value.devices === 'object' ? (value.devices as Dict) : {},
  ui: value.ui && typeof value.ui === 'object' ? (value.ui as Dict) : {},
})

const hints = (entry: Entry, section: string): Hint[] => {
  const uiHints = entry.ui.hints
  if (!uiHints || typeof uiHints !== 'object') return []
  const value = (uiHints as Dict)[section]
  return Array.isArray(value) ? (value as Hint[]) : []
}

const fieldSpan = (hint: Hint) => configurationFieldSpan(hint.component, hint.width)

const valueFor = (entry: Entry, section: string, field: string) => {
  const value = entry[section]
  return value && typeof value === 'object' ? (value as Dict)[field] : undefined
}

const setValue = async (entry: Entry, section: string, field: string, value: unknown) => {
  if (saving.value) return false
  const sectionValue = entry[section]
  const previous =
    sectionValue && typeof sectionValue === 'object' ? (sectionValue as Dict)[field] : undefined
  entry[section] = {
    ...(sectionValue && typeof sectionValue === 'object' ? sectionValue : {}),
    [field]: value,
  }
  saving.value = `${entry.uid}:${section}:${field}`
  try {
    await api.updateGame({ gameId: entry.uid, data: { [section]: { [field]: value } } })
    return true
  } catch (error) {
    entry[section] = { ...(entry[section] as Dict), [field]: previous }
    message.error(apiErrorMessage(error, t('emulator.toast.saveFailed')))
    return false
  } finally {
    saving.value = null
  }
}

const trigger = async (entry: Entry, section: string, field: string) => {
  if (await setValue(entry, section, field, true)) await load()
}

const {
  loading,
  error: loadError,
  execute: load,
} = useApiQuery(
  async () => {
    const [gameResult, typeResult] = await Promise.all([api.getGames(), api.getTypes()])
    const data = gameResult.data || {}
    rows.value = (gameResult.order || []).map(item =>
      normalize(item.uid, item.type, (data[item.uid] || {}) as Dict)
    )
    types.value = (typeResult.data || []) as typeof types.value
    if (!rows.value.some(entry => entry.uid === activeKey.value))
      activeKey.value = rows.value[0]?.uid || ''
    return true
  },
  () => t('emulator.toast.loadFailed')
)

const createGame = async () => {
  try {
    await api.addGame(selectedType.value)
    createOpen.value = false
    selectedType.value = ''
    message.success(t('emulator.toast.addOk'))
    await load()
  } catch (error) {
    message.error(apiErrorMessage(error, t('emulator.toast.addFailed')))
  }
}

const search = async () => {
  searchLoading.value = true
  try {
    const result = await api.searchGames()
    searchRows.value = Object.entries(result.data || {}).map(([uid, value]) => ({
      uid,
      ...(value as Dict),
    })) as SearchRow[]
    if (searchRows.value.length === 0) message.info(t('emulator.searchEmpty'))
    else message.success(t('emulator.toast.searchFound', { count: searchRows.value.length }))
  } catch (error) {
    message.error(apiErrorMessage(error, t('emulator.toast.searchFailed')))
  } finally {
    searchLoading.value = false
  }
}

const addSearchResult = async (uid: string) => {
  try {
    await api.addSearchResult(uid)
    searchRows.value = searchRows.value.filter(item => item.uid !== uid)
    await load()
  } catch (error) {
    message.error(apiErrorMessage(error, t('emulator.toast.addFailed')))
  }
}

const deviceEntries = (entry: Entry) => {
  const order = Array.isArray(entry.devices.order)
    ? (entry.devices.order as Array<{ uid: string; type: string }>)
    : []
  const data =
    entry.devices.data && typeof entry.devices.data === 'object' ? (entry.devices.data as Dict) : {}
  return order.map(item => ({
    uid: item.uid,
    type: item.type,
    ...((data[item.uid] || {}) as Dict),
  }))
}

const deviceInfoHints = (entry: Entry) => {
  const first = deviceEntries(entry)[0]
  const order = ['index', 'status', 'name', 'adb_address']
  return first
    ? [...hints(first as unknown as Entry, 'info')].sort((a, b) => {
        const ai = order.indexOf(a.field || '')
        const bi = order.indexOf(b.field || '')
        return (ai < 0 ? order.length : ai) - (bi < 0 ? order.length : bi)
      })
    : []
}

const deviceActionHints = (device: Dict) => {
  return hints(device as unknown as Entry, 'action')
}

const deviceValue = (device: Dict, field: string) => {
  const info = device.info
  return info && typeof info === 'object' ? (info as Dict)[field] : undefined
}

const updateDevice = async (
  entry: Entry,
  device: Dict,
  section: string,
  field: string,
  value: unknown
) => {
  if (deviceSaving.value) return false
  deviceSaving.value = `${entry.uid}:${device.uid}:${section}:${field}`
  try {
    await api.updateDevice({
      gameId: entry.uid,
      deviceId: String(device.uid),
      data: { [section]: { [field]: value } },
    })
    await load()
    return true
  } catch (error) {
    message.error(apiErrorMessage(error, t('emulator.toast.saveFailed')))
    return false
  } finally {
    deviceSaving.value = null
  }
}

const pickPath = async (entry: Entry, field: string, pathKind?: string | null) => {
  if (!window.electronAPI) {
    message.error(t('emulator.toast.filePickerUnavailable'))
    return
  }
  try {
    const selected =
      pathKind === 'folder'
        ? await window.electronAPI.selectFolder()
        : ((
            await window.electronAPI.selectFile([
              { name: t('emulator.allFiles'), extensions: ['*'] },
            ])
          )?.[0] ?? null)
    if (selected) await setValue(entry, 'info', field, selected)
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error))
  }
}

const runDeviceAction = (entry: Entry, device: Dict, field: string) => {
  const run = () => updateDevice(entry, device, 'action', field, true)
  if (field !== 'delete_instance') {
    void run()
    return
  }
  Modal.confirm({
    title: t('emulator.deviceDeleteConfirm'),
    okText: t('emulator.ok'),
    cancelText: t('emulator.cancel'),
    okType: 'danger',
    onOk: async () => {
      if (!(await run())) throw new Error(t('emulator.toast.saveFailed'))
    },
  })
}

watch(activeKey, key => {
  if (key) localStorage.setItem('games_active_key', key)
})

onMounted(load)
</script>

<template>
  <main class="games-page">
    <div class="page-header">
      <h1>{{ t('emulator.title') }}</h1>
      <div class="games-page-actions">
        <a-button :loading="searchLoading" @click="search"
          ><template #icon><SearchOutlined /></template>{{ t('emulator.autoSearch') }}</a-button
        >
        <a-button type="primary" @click="createOpen = true"
          ><template #icon><PlusOutlined /></template>{{ t('emulator.manualAdd') }}</a-button
        >
      </div>
    </div>

    <div class="page-content">
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <div v-if="searchRows.length" class="search-panel">
        <div class="search-panel-heading">
          <div>
            <div class="section-title">{{ t('emulator.searchModalTitle') }}</div>
            <div class="section-description">{{ t('emulator.searchResultHint') }}</div>
          </div>
          <a-button type="text" size="small" @click="searchRows = []">{{
            t('emulator.clearSearch')
          }}</a-button>
        </div>
        <a-space wrap>
          <a-button
            v-for="item in searchRows"
            :key="item.uid"
            size="small"
            @click="addSearchResult(item.uid)"
          >
            <PlusOutlined /> {{ item.name || item.type || item.uid }}
          </a-button>
        </a-space>
      </div>

      <a-spin v-if="loading && !rows.length" class="games-loading" />
      <a-empty v-else-if="!rows.length && !loadError" :description="t('emulator.noDevice')" />
      <div v-else-if="rows.length" class="emulator-tabs">
        <a-tabs v-model:active-key="activeKey" type="card" class="game-tabs">
          <a-tab-pane v-for="entry in rows" :key="entry.uid">
            <template #tab>
              <span class="game-tab-label">{{
                String(entry.info.name || t('emulator.unnamed'))
              }}</span>
            </template>

            <section class="config-section">
              <div class="section-header">
                <h3>{{ t('emulator.configTitle') }}</h3>
              </div>
              <div class="form-grid-24">
                <div
                  v-for="hint in hints(entry, 'info')"
                  :key="`info-${hint.field}`"
                  class="form-grid-24__item form-item-vertical"
                  :style="{ '--field-span': fieldSpan(hint) }"
                >
                  <div class="form-label-wrapper">
                    <span class="form-label">{{ fieldLabel(hint.field || '') }}</span>
                    <a-tooltip
                      v-if="fieldHelp(hint.field || '')"
                      :title="fieldHelp(hint.field || '')"
                    >
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </div>
                  <DeclarativeControl
                    :component="hint.component"
                    :label="fieldLabel(hint.field || '')"
                    :model-value="valueFor(entry, 'info', hint.field || '')"
                    :disabled="
                      hint.editable === false || saving === `${entry.uid}:info:${hint.field}`
                    "
                    :loading="saving === `${entry.uid}:info:${hint.field}`"
                    :min="hint.min"
                    :max="hint.max"
                    :options="hint.options"
                    :path-kind="hint.path_kind"
                    @update:model-value="value => setValue(entry, 'info', hint.field || '', value)"
                    @pick="pickPath(entry, hint.field || '', hint.path_kind)"
                  />
                </div>
              </div>
            </section>

            <section class="device-section">
              <div class="section-header device-heading">
                <h3>{{ t('emulator.deviceList') }}</h3>
                <div class="section-actions">
                  <a-tooltip
                    v-for="hint in hints(entry, 'action')"
                    :key="`action-${hint.field}`"
                    :title="actionLabel(hint.field || '')"
                  >
                    <a-button
                      type="text"
                      shape="circle"
                      :aria-label="actionLabel(hint.field || '')"
                      :loading="saving === `${entry.uid}:action:${hint.field}`"
                      :disabled="hint.editable === false"
                      @click="trigger(entry, 'action', hint.field || '')"
                      ><component :is="actionIcon(hint.field || '')"
                    /></a-button>
                  </a-tooltip>
                </div>
              </div>
              <a-table
                v-if="deviceEntries(entry).length"
                :data-source="deviceEntries(entry)"
                row-key="uid"
                :pagination="false"
                size="small"
                :scroll="{ x: 720 }"
              >
                <a-table-column
                  v-for="hint in deviceInfoHints(entry)"
                  :key="hint.field"
                  :title="fieldLabel(hint.field || '')"
                  :width="hint.field === 'index' ? 80 : hint.field === 'name' ? 220 : 150"
                >
                  <template #default="{ record }">
                    <a-tag
                      v-if="hint.field === 'status'"
                      :color="statusColor(deviceValue(record, hint.field || ''))"
                      >{{ statusText(deviceValue(record, hint.field || '')) }}</a-tag
                    >
                    <span v-else>{{
                      hint.field === 'index'
                        ? `#${String(deviceValue(record, hint.field || '') ?? '-')}`
                        : String(deviceValue(record, hint.field || '') ?? '-')
                    }}</span>
                  </template>
                </a-table-column>
                <a-table-column
                  key="actions"
                  :title="t('emulator.colAction')"
                  :width="220"
                  align="right"
                >
                  <template #default="{ record }">
                    <a-space :size="2">
                      <a-tooltip
                        v-for="hint in deviceActionHints(record)"
                        :key="hint.field"
                        :title="actionLabel(hint.field || '')"
                      >
                        <a-button
                          type="text"
                          shape="circle"
                          size="small"
                          :aria-label="actionLabel(hint.field || '')"
                          :danger="hint.field === 'delete_instance'"
                          :loading="
                            deviceSaving === `${entry.uid}:${record.uid}:action:${hint.field}`
                          "
                          :disabled="hint.editable === false"
                          @click="runDeviceAction(entry, record, hint.field || '')"
                          ><component :is="actionIcon(hint.field || '')"
                        /></a-button>
                      </a-tooltip>
                    </a-space>
                  </template>
                </a-table-column>
              </a-table>
              <a-empty v-else :image="false" :description="t('emulator.noDevice')" />
            </section>
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>

    <a-modal
      v-model:open="createOpen"
      :title="t('emulator.manualAdd')"
      :ok-text="t('emulator.ok')"
      :cancel-text="t('emulator.cancel')"
      @ok="createGame"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('emulator.typeLabel')">
          <a-select
            v-model:value="selectedType"
            :options="
              types.map(item => ({ value: item.name, label: item.display_name || item.name }))
            "
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </main>
</template>

<style scoped>
.games-page {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--ant-color-bg-layout);
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 0;
}
.page-header h1 {
  margin: 0 0 8px;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.page-content {
  flex: 1;
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}
.games-page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.emulator-tabs {
  flex: 1;
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  padding: 16px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.emulator-tabs :deep(.ant-tabs) {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}
.emulator-tabs :deep(.ant-tabs-content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.emulator-tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
  overflow: auto;
}
.search-panel {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
}
.search-panel-heading,
.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.search-panel-heading {
  margin-bottom: 12px;
}
.section-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}
.section-description,
.section-heading p {
  margin: 4px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}
.game-tabs {
  min-height: 0;
}
.game-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 16px;
}
.game-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.config-section,
.device-section {
  flex-shrink: 0;
  margin-bottom: 16px;
  padding: 16px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}
.section-header h3 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.games-loading {
  display: flex;
  min-height: 240px;
  align-items: center;
  justify-content: center;
}
.device-section :deep(.ant-table-wrapper) {
  margin-top: 16px;
}
.device-section :deep(.ant-empty) {
  margin: 24px 0 8px;
}
@media (max-width: 768px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }
  .games-page-actions {
    flex-wrap: wrap;
  }
  .emulator-tabs {
    padding: 12px;
  }
  .config-section,
  .device-section {
    padding: 12px;
  }
}
@media (max-width: 600px) {
  .device-heading {
    align-items: flex-start;
  }
}
</style>
