<template>
  <div class="emulator-tab">
    <div class="emulator-toolbar">
      <a-select
        :value="activeKey || undefined"
        class="emulator-select"
        placeholder="选择模拟器配置"
        :options="emulatorSelectOptions"
        :loading="loading"
        @change="handleEmulatorSelection"
      />
      <a-space class="action-buttons" wrap>
        <a-button type="primary" size="small" @click="onAddEmulator">
          <template #icon><PlusOutlined /></template>
          新建
        </a-button>
        <a-button :loading="searching" size="small" @click="onSearchEmulator">
          <template #icon><SearchOutlined /></template>
          搜索
        </a-button>
        <a-button :loading="loading" size="small" @click="onRefresh">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </a-space>
    </div>

    <div class="emulator-scroll">
      <template v-for="emulator in emulatorIndex" :key="emulator.uid">
        <a-spin :spinning="loading || loadingDevices.has(emulator.uid)" tip="加载中...">
          <div v-if="activeKey === emulator.uid" class="emulator-config-panel">
            <div class="config-section">
              <div class="section-header">
                <h3>基础配置</h3>
                <a-space size="small">
                  <a-spin v-if="savingMap.get(emulator.uid)" size="small" />
                  <a-popconfirm
                    title="只删除此模拟器配置，不会卸载模拟器。确认继续？"
                    ok-text="删除"
                    cancel-text="取消"
                    @confirm="onDeleteEmulator(emulator.uid)"
                  >
                    <a-button
                      danger
                      type="text"
                      size="small"
                      :loading="savingMap.get(emulator.uid)"
                      :aria-label="`删除 ${emulatorData[emulator.uid]?.Info?.Name || '模拟器'} 配置`"
                    >
                      <template #icon><DeleteOutlined /></template>
                      删除配置
                    </a-button>
                  </a-popconfirm>
                </a-space>
              </div>
              <a-form layout="vertical" class="config-form">
                <a-row :gutter="16">
                  <a-col :span="12">
                    <a-form-item label="模拟器名称">
                      <a-input
                        v-model:value="getEditingData(emulator.uid).name"
                        placeholder="请输入模拟器名称"
                        allow-clear
                        @blur="onSaveName(emulator.uid)"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :span="12">
                    <a-form-item label="模拟器类型">
                      <a-select
                        v-model:value="getEditingData(emulator.uid).type"
                        placeholder="请选择模拟器类型"
                        :options="emulatorTypeOptions"
                        @change="(v: any) => onSaveType(emulator.uid, v)"
                      />
                    </a-form-item>
                  </a-col>
                </a-row>

                <a-row :gutter="16">
                  <a-col :span="16">
                    <a-form-item label="模拟器路径">
                      <a-input
                        v-model:value="getEditingData(emulator.uid).path"
                        placeholder="请选择模拟器路径"
                        allow-clear
                        @blur="onSavePath(emulator.uid)"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8" class="path-button-col">
                    <a-form-item label=" ">
                      <a-button block @click="onSelectPath(emulator.uid)">
                        <template #icon><FolderOpenOutlined /></template>
                        选择路径
                      </a-button>
                    </a-form-item>
                  </a-col>
                </a-row>

                <a-row :gutter="16">
                  <a-col :span="8">
                    <a-form-item label="最大等待时间（秒）">
                      <a-input-number
                        v-model:value="getEditingData(emulator.uid).max_wait_time"
                        :min="1"
                        :max="9999"
                        :step="5"
                        style="width: 100%"
                        @blur="onSaveMaxWaitTime(emulator.uid)"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col v-if="getEditingData(emulator.uid).type === 'mumu'" :span="8">
                    <a-form-item label="强力关闭 MuMu">
                      <a-switch
                        v-model:checked="getEditingData(emulator.uid).force_kill_on_close"
                        checked-children="是"
                        un-checked-children="否"
                        @change="(v: boolean) => onSaveForceKill(emulator.uid, v)"
                      />
                    </a-form-item>
                  </a-col>
                </a-row>

                <a-row v-if="getEditingData(emulator.uid).type !== 'mumu'" :gutter="16">
                  <a-col :span="24">
                    <a-form-item label="老板键">
                      <a-input-group compact>
                        <a-input
                          v-model:value="bossKeyInputMap[emulator.uid]"
                          :placeholder="
                            recordingBossKeyMap.get(emulator.uid)
                              ? '请按下快捷键...'
                              : '例如: Ctrl+Alt+H'
                          "
                          style="width: calc(100% - 160px)"
                          :disabled="recordingBossKeyMap.get(emulator.uid)"
                          @input="onBossKeyInput(emulator.uid)"
                          @press-enter="onSetBossKey(emulator.uid)"
                        />
                        <a-button
                          v-if="!recordingBossKeyMap.get(emulator.uid)"
                          type="primary"
                          style="width: 80px"
                          @click="onStartRecordBossKey(emulator.uid)"
                        >
                          <template #icon><KeyOutlined /></template>
                          录制
                        </a-button>
                        <a-button
                          v-else
                          danger
                          style="width: 80px"
                          @click="onCancelRecordBossKey(emulator.uid)"
                        >
                          取消
                        </a-button>
                        <a-button style="width: 80px" @click="onSetBossKey(emulator.uid)">
                          保存
                        </a-button>
                      </a-input-group>
                    </a-form-item>
                  </a-col>
                </a-row>
                <a-alert
                  v-else
                  type="info"
                  show-icon
                  message="MuMu 模拟器无需配置老板键；可按需启用上方强力关闭。"
                />
              </a-form>
            </div>

            <div class="devices-section">
              <div class="section-header">
                <h3>设备列表</h3>
                <a-button size="small" type="link" @click="onRefreshDevices(emulator.uid)">
                  <template #icon><ReloadOutlined /></template>
                  刷新设备
                </a-button>
              </div>

              <a-alert
                v-if="pollingErrors[emulator.uid]"
                type="warning"
                show-icon
                :message="`设备状态刷新失败：${pollingErrors[emulator.uid]}`"
                class="poll-error-alert"
              />

              <a-empty
                v-if="
                  !devicesData[emulator.uid] || Object.keys(devicesData[emulator.uid]).length === 0
                "
                description="暂无设备信息"
              >
                <template #extra>
                  <a-space>
                    <a-button size="small" @click="onRefreshDevices(emulator.uid)">
                      <template #icon><ReloadOutlined /></template>
                      刷新设备
                    </a-button>
                    <a-tooltip
                      :title="getEmptyDeviceStartState(emulator).reason"
                      :disabled="!getEmptyDeviceStartState(emulator).disabled"
                    >
                      <a-button
                        type="primary"
                        size="small"
                        :loading="getEmptyDeviceStartState(emulator).loading"
                        :disabled="getEmptyDeviceStartState(emulator).disabled"
                        @click="onStartDevice(emulator.uid, '0')"
                      >
                        启动实例 0
                      </a-button>
                    </a-tooltip>
                  </a-space>
                </template>
              </a-empty>

              <div v-else class="device-list">
                <a-table
                  :columns="deviceColumns"
                  :data-source="getDeviceList(emulator.uid)"
                  :pagination="false"
                  size="small"
                  row-key="index"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'status'">
                      <a-tag :color="getDeviceStatusInfo(record.status).color">
                        {{ getDeviceStatusInfo(record.status).text }}
                      </a-tag>
                    </template>
                    <template v-else-if="column.key === 'name'">
                      <span>{{ record.title || record.adb_address || '-' }}</span>
                    </template>
                    <template v-else-if="column.key === 'adb'">
                      <a-typography-paragraph
                        v-if="record.adb_address"
                        copyable
                        :ellipsis="{ rows: 1 }"
                        style="margin: 0; max-width: 200px"
                      >
                        {{ record.adb_address }}
                      </a-typography-paragraph>
                      <span v-else>-</span>
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-space>
                        <a-tooltip
                          :title="getActionState('open', emulator, record).reason"
                          :disabled="
                            !getActionState('open', emulator, record).disabled ||
                            getActionState('open', emulator, record).loading
                          "
                        >
                          <a-button
                            type="primary"
                            size="small"
                            :loading="getActionState('open', emulator, record).loading"
                            :disabled="getActionState('open', emulator, record).disabled"
                            @click="onStartDevice(emulator.uid, record.index)"
                          >
                            启动
                          </a-button>
                        </a-tooltip>
                        <a-tooltip
                          :title="getActionState('close', emulator, record).reason"
                          :disabled="
                            !getActionState('close', emulator, record).disabled ||
                            getActionState('close', emulator, record).loading
                          "
                        >
                          <a-button
                            danger
                            size="small"
                            :loading="getActionState('close', emulator, record).loading"
                            :disabled="getActionState('close', emulator, record).disabled"
                            @click="onStopDevice(emulator.uid, record.index)"
                          >
                            关闭
                          </a-button>
                        </a-tooltip>
                        <a-tooltip
                          :title="getActionState('show', emulator, record).reason"
                          :disabled="
                            !getActionState('show', emulator, record).disabled ||
                            getActionState('show', emulator, record).loading
                          "
                        >
                          <a-button
                            size="small"
                            :loading="getActionState('show', emulator, record).loading"
                            :disabled="getActionState('show', emulator, record).disabled"
                            @click="onShowDevice(emulator.uid, record.index)"
                          >
                            显示
                          </a-button>
                        </a-tooltip>
                      </a-space>
                    </template>
                  </template>
                </a-table>
              </div>
            </div>
          </div>
        </a-spin>
      </template>

      <div v-if="emulatorIndex.length === 0" class="emulator-empty">
        <a-empty description="暂无模拟器配置，点击右上角「新建」或「搜索」按钮添加模拟器">
          <a-button type="primary" @click="onAddEmulator">
            <template #icon><PlusOutlined /></template>
            新建模拟器
          </a-button>
        </a-empty>
      </div>
    </div>

    <a-modal v-model:open="showSearchModal" title="搜索已安装的模拟器" :footer="null" width="600px">
      <a-spin :spinning="searching" tip="搜索中...">
        <a-empty
          v-if="searchResults.length === 0 && !searching"
          description="未找到已安装的模拟器"
        />
        <div v-else class="search-results">
          <div v-for="result in searchResults" :key="result.path" class="search-result-item">
            <div class="result-info">
              <div class="result-name">
                <DesktopOutlined /> {{ result.name }}
                <a-tag color="blue" class="result-type">{{ result.type }}</a-tag>
              </div>
              <div class="result-path">{{ result.path }}</div>
            </div>
            <a-button type="primary" size="small" @click="onImportResult(result)"> 导入 </a-button>
          </div>
        </div>
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import {
  PlusOutlined,
  SearchOutlined,
  ReloadOutlined,
  FolderOpenOutlined,
  KeyOutlined,
  DesktopOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import type { EmulatorSearchResult, DeviceInfo } from '@/api'
import {
  useEmulatorManagement,
  emulatorTypeOptions,
  getDeviceStatusInfo,
  getDeviceActionState,
  DeviceStatus,
  type EmulatorType,
} from '@/composables/useEmulatorApi'

const {
  loading,
  searching,
  emulatorIndex,
  emulatorData,
  searchResults,
  showSearchModal,
  devicesData,
  loadingDevices,
  savingMap,
  startingDevices,
  stoppingDevices,
  showingDevices,
  bossKeyInputMap,
  activeKey,
  recordingBossKeyMap,
  pollingErrors,
  loadEmulators,
  getEditingData,
  handleSaveChange,
  handleAdd,
  handleDelete,
  handleSearch,
  handleImportFromSearch,
  loadDevices,
  startEmulator,
  stopEmulator,
  showEmulator,
  selectEmulatorPath,
  onTabChange,
  onEmulatorsLoaded,
  startPolling,
  stopPolling,
  startRecordBossKey,
  cancelRecordBossKey,
  handleSetBossKey,
  handleBossKeyInputChange,
} = useEmulatorManagement()

const deviceColumns = [
  { title: '索引', dataIndex: 'index', key: 'index', width: 80 },
  { title: '名称', key: 'name', width: 150 },
  { title: 'ADB地址', key: 'adb', width: 220 },
  { title: '状态', key: 'status', width: 100 },
  { title: '操作', key: 'action', width: 200 },
]

const getDeviceList = (uuid: string): (DeviceInfo & { index: string })[] => {
  const devices = devicesData.value[uuid] || {}
  return Object.entries(devices).map(([index, info]) => ({
    index,
    ...info,
  }))
}

const getOnlineDeviceCount = (uuid: string): number => {
  const devices = devicesData.value[uuid] || {}
  return Object.values(devices).filter((d: DeviceInfo) => d.status === 0).length
}

const emulatorSelectOptions = computed(() =>
  emulatorIndex.value.map(emulator => {
    const devices = devicesData.value[emulator.uid] || {}
    return {
      value: emulator.uid,
      label: `${emulatorData.value[emulator.uid]?.Info?.Name || '未命名模拟器'} · ${getOnlineDeviceCount(emulator.uid)}/${Object.keys(devices).length} 在线`,
    }
  })
)

const handleEmulatorSelection = (value: string | number) => {
  onTabChange(String(value))
}

const getActionState = (
  operation: 'open' | 'close' | 'show',
  emulator: (typeof emulatorIndex.value)[number],
  record: DeviceInfo & { index: string }
) => {
  const editData = getEditingData(emulator.uid)
  const emulatorType = (editData.type as EmulatorType) || ''
  const hasPath = Boolean(editData.path)
  const deviceKey = `${emulator.uid}-${record.index}`
  const inFlight =
    operation === 'open'
      ? startingDevices.value.has(deviceKey)
      : operation === 'close'
        ? stoppingDevices.value.has(deviceKey)
        : showingDevices.value.has(deviceKey)
  return getDeviceActionState(operation, record.status, emulatorType, hasPath, inFlight)
}

const getEmptyDeviceStartState = (emulator: (typeof emulatorIndex.value)[number]) => {
  const editData = getEditingData(emulator.uid)
  const deviceKey = `${emulator.uid}-0`
  return getDeviceActionState(
    'open',
    DeviceStatus.NOT_FOUND,
    (editData.type as EmulatorType) || '',
    Boolean(editData.path),
    startingDevices.value.has(deviceKey)
  )
}

const onRefresh = async () => {
  await loadEmulators()
  await onEmulatorsLoaded()
}

const onAddEmulator = async () => {
  const newId = await handleAdd()
  if (newId) {
    activeKey.value = newId
    await loadDevices(newId)
  }
}

const onSearchEmulator = async () => {
  await handleSearch()
}

const onImportResult = async (result: EmulatorSearchResult) => {
  const newId = await handleImportFromSearch(result)
  if (newId) {
    activeKey.value = newId
    await loadDevices(newId)
  }
}

const onRefreshDevices = async (uuid: string) => {
  await loadDevices(uuid)
}

const onStartDevice = async (uuid: string, index: string) => {
  await startEmulator(uuid, index)
}

const onStopDevice = async (uuid: string, index: string) => {
  await stopEmulator(uuid, index)
}

const onShowDevice = async (uuid: string, index: string) => {
  await showEmulator(uuid, index)
}

const onSelectPath = async (uuid: string) => {
  await selectEmulatorPath(uuid)
}

const onSaveName = async (uuid: string) => {
  const data = getEditingData(uuid)
  if (data.name !== (emulatorData.value[uuid]?.Info?.Name || '')) {
    await handleSaveChange(uuid, 'name', data.name)
  }
}

const onSaveType = async (uuid: string, value: EmulatorType) => {
  await handleSaveChange(uuid, 'type', value)
}

const onSavePath = async (uuid: string) => {
  const data = getEditingData(uuid)
  if (data.path !== (emulatorData.value[uuid]?.Info?.Path || '')) {
    await handleSaveChange(uuid, 'path', data.path)
  }
}

const onSaveMaxWaitTime = async (uuid: string) => {
  const data = getEditingData(uuid)
  if (data.max_wait_time !== (emulatorData.value[uuid]?.Info?.MaxWaitTime || 300)) {
    await handleSaveChange(uuid, 'max_wait_time', data.max_wait_time)
  }
}

const onSaveForceKill = async (uuid: string, value: boolean) => {
  await handleSaveChange(uuid, 'force_kill_on_close', value)
}

const onStartRecordBossKey = (uuid: string) => {
  startRecordBossKey(uuid)
}

const onCancelRecordBossKey = (uuid: string) => {
  cancelRecordBossKey(uuid)
}

const onSetBossKey = async (uuid: string) => {
  await handleSetBossKey(uuid)
}

const onBossKeyInput = (uuid: string) => {
  handleBossKeyInputChange(uuid)
}

const onDeleteEmulator = async (uuid: string) => {
  await handleDelete(uuid)
}

onMounted(async () => {
  await loadEmulators()
  await onEmulatorsLoaded()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.emulator-tab {
  height: 100%;
  min-height: 0;
  min-width: 0;
  container: emulator-content / inline-size;
  padding: var(--v6-space-1) 0 var(--v6-space-3);
  display: flex;
  flex-direction: column;
}

.emulator-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
  margin-bottom: var(--v6-space-2);
  padding: var(--v6-space-2) 0 var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.emulator-select {
  width: min(420px, 55%);
}

.emulator-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 2px var(--v6-space-3) 0;
}

.emulator-empty {
  min-height: 168px;
  display: grid;
  place-items: center;
}

.action-buttons {
  margin-right: 2px;
}

.emulator-config-panel {
  display: grid;
  gap: var(--v6-space-3);
}

.config-section,
.devices-section {
  padding: var(--v6-space-4);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-surface) 82%, transparent);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--v6-space-3);
  margin-bottom: var(--v6-space-3);
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.config-form {
  width: 100%;
  max-width: none;
}

.config-form :deep(.ant-form-item) {
  margin-bottom: var(--v6-space-3);
}

.config-form :deep(.ant-form-item-label) {
  padding-bottom: 4px;
}

.config-form :deep(.ant-form-item-label > label) {
  color: var(--v6-color-text-secondary);
  font-size: 12px;
}

.path-button-col {
  display: flex;
  align-items: flex-end;
}

.devices-section {
  min-height: 220px;
}

.device-list {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: 10px;
}

.device-list :deep(.ant-table),
.device-list :deep(.ant-table-cell) {
  background: transparent;
}

.device-list :deep(.ant-table-thead > tr > th) {
  padding: 8px 10px;
  color: var(--v6-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
  background: color-mix(in srgb, var(--v6-color-fill-tertiary) 58%, transparent);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.device-list :deep(.ant-table-tbody > tr > td) {
  padding: 8px 10px;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.device-list :deep(.ant-table-tbody > tr:last-child > td) {
  border-bottom: none;
}

.device-list :deep(.ant-table-tbody > tr:hover > td) {
  background: color-mix(in srgb, var(--v6-color-primary) 5%, transparent);
}

.poll-error-alert {
  margin-bottom: var(--v6-space-3);
}

.search-results {
  max-height: 400px;
  overflow-y: auto;
}

.search-result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: 10px;
  background: color-mix(in srgb, var(--v6-color-surface) 84%, transparent);
  transition:
    border-color var(--v6-motion-fast) var(--v6-ease-out),
    background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.search-result-item:hover {
  border-color: color-mix(in srgb, var(--v6-color-primary) 45%, var(--v6-color-border-subtle));
  background: color-mix(in srgb, var(--v6-color-primary) 6%, var(--v6-color-surface));
}

.result-info {
  flex: 1;
  min-width: 0;
}

.result-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  margin-bottom: 4px;
}

.result-type {
  margin-left: auto;
}

.result-path {
  font-size: 12px;
  color: var(--v6-color-text-secondary);
  word-break: break-all;
}

:root[data-perf-mode='low'] .config-section,
:root[data-perf-mode='low'] .devices-section {
  backdrop-filter: none;
}

@media (prefers-reduced-motion: reduce) {
  .search-result-item {
    transition: none;
  }

  .config-section,
  .devices-section {
    backdrop-filter: none;
  }
}

/* .emulator-tab 自身规则须由外层 game-center 根的 game-emulator 容器驱动
   (@container 不能命中声明容器的元素自身) */
@container game-emulator (max-width: 820px) {
  .emulator-tab {
    padding: var(--v6-space-2);
  }
}

@container emulator-content (max-width: 820px) {
  .emulator-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .emulator-select {
    width: 100%;
  }

  .config-section,
  .devices-section {
    padding: var(--v6-space-3);
  }
}
</style>
