<template>
  <div class="target-workspace" :class="{ 'target-workspace--narrow': narrow }">
    <GameTargetHeader :game="game" @create-instance="creating = true" />

    <div
      v-if="activeOperations.length || game.runtime.recoveryPending?.length"
      class="detail-banners"
    >
      <a-alert
        v-for="item in activeOperations"
        :key="item.taskId"
        type="info"
        show-icon
        :message="t('core.games.operationRunning')"
      >
        <template #action>
          <a-button :loading="item.cancelling" @click="emit('cancel', item)">
            {{ t('core.games.cancel') }}
          </a-button>
        </template>
      </a-alert>
      <a-alert
        v-if="game.runtime.recoveryPending?.length"
        type="warning"
        show-icon
        :message="t('core.games.recoveryHint')"
      />
    </div>

    <section class="devices-panel app-page-section">
      <header class="section-head">
        <h3>
          {{
            t(
              hasMaintenance && activeSubTab === 'maintenance'
                ? 'core.games.maintenance'
                : 'core.emulator.deviceList'
            )
          }}
        </h3>
        <a-segmented
          v-if="hasMaintenance"
          v-model:value="activeSubTab"
          :options="maintenanceSubTabs"
        />
      </header>

      <ModAvdMaintenance v-if="hasMaintenance && activeSubTab === 'maintenance'" :game="game" />

      <a-table
        v-else
        :columns="deviceColumns"
        :data-source="devices"
        row-key="uid"
        :pagination="false"
        :scroll="tableScroll"
        :size="narrow ? 'small' : 'middle'"
      >
        <template #emptyText>
          <NoData :description="t('core.emulator.noDevice')" size="sm" />
        </template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <span class="device-name">
              {{ record.document.info?.name || t('core.emulator.unnamed') }}
            </span>
            <span
              v-if="
                record.document.info &&
                'index' in record.document.info &&
                record.document.info.index !== null &&
                record.document.info.index !== undefined
              "
              class="native-index"
            >
              #{{ record.document.info.index }}
            </span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-space :size="4" wrap>
              <StatusChip :tone="deviceStatusTone(record.document)">
                {{ statusLabel(record.document) }}
              </StatusChip>
              <StatusChip v-if="isRecoveryPending(record.uid)" tone="warning" :dot="false">
                {{ t('core.games.recoveryShort') }}
              </StatusChip>
            </a-space>
          </template>
          <template v-else-if="column.key === 'adb'">
            <span class="adb-text">{{ record.document.info?.adb_address || '—' }}</span>
          </template>
          <template v-else-if="column.key === 'usage'">
            <span v-if="game.runtime.deviceUsage?.[record.uid]" class="usage-text">
              <span class="usage-dot" aria-hidden="true" />
              <span class="usage-label" :title="game.runtime.deviceUsage[record.uid]">
                {{ game.runtime.deviceUsage[record.uid] }}
              </span>
            </span>
            <span v-else class="muted-text">{{ t('core.games.available') }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <DeviceActions
              :game="game"
              :device="record"
              :narrow="narrow"
              @edit="kind => (deviceEditing = { device: record, kind })"
            />
          </template>
        </template>
      </a-table>
    </section>

    <GameEditor
      :open="true"
      :row="game"
      :types="[]"
      @dirty-change="(uid, dirty) => emit('dirtyChange', uid, dirty)"
    />

    <DeviceSettings
      v-if="deviceEditing"
      :open="true"
      :game="game"
      :device="deviceEditing.device"
      :kind="deviceEditing.kind"
      @close="deviceEditing = undefined"
    />
    <CreateInstance v-if="creating" :open="true" :game="game" @close="creating = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NoData, StatusChip } from '@/components/ui'
import type { ActiveTriggerField, DeviceStatus } from '@/api'
import type { GameDevice, GameDeviceRow, GameRow } from '@/types/games'
import { gameDevices } from '@/types/games'
import { deviceStatusTone, hasModAvdMaintenance } from '../gamePresentation'
import CreateInstance from './CreateInstance.vue'
import DeviceActions from './DeviceActions.vue'
import DeviceSettings from './DeviceSettings.vue'
import GameEditor from './GameEditor.vue'
import GameTargetHeader from './GameTargetHeader.vue'
import ModAvdMaintenance from './ModAvdMaintenance.vue'

const props = withDefaults(
  defineProps<{
    game: GameRow
    activeOperations?: readonly ActiveTriggerField[]
    narrow?: boolean
  }>(),
  { activeOperations: () => [], narrow: false }
)
const emit = defineEmits<{
  cancel: [field: ActiveTriggerField]
  dirtyChange: [uid: string, dirty: boolean]
}>()
const { t } = useI18n()
const creating = ref(false)
const activeSubTab = ref<'devices' | 'maintenance'>('devices')
const deviceEditing = ref<{ device: GameDeviceRow; kind: 'settings' | 'connection' | 'options' }>()

const devices = computed(() => gameDevices(props.game))
const hasMaintenance = computed(() => hasModAvdMaintenance(props.game))
const maintenanceSubTabs = computed(() => [
  { label: t('core.emulator.deviceList'), value: 'devices' },
  { label: t('core.games.maintenance'), value: 'maintenance' },
])

watch(
  () => props.game.uid,
  () => {
    activeSubTab.value = 'devices'
  }
)

const statusLabels = computed<Record<DeviceStatus, string>>(() => ({
  0: t('core.games.states.0'),
  1: t('core.games.states.1'),
  2: t('core.games.states.2'),
  3: t('core.games.states.3'),
  4: t('core.games.states.4'),
  5: t('core.games.states.5'),
  6: t('core.games.states.6'),
  7: t('core.games.states.7'),
  10: t('core.games.states.10'),
}))

const deviceColumns = computed(() => [
  { title: t('core.games.device'), key: 'name', width: props.narrow ? 128 : undefined },
  { title: t('core.games.status'), key: 'status', width: props.narrow ? 88 : 136 },
  ...(props.game.type.kind === 'emulator'
    ? [{ title: t('core.emulator.colAdb'), key: 'adb', width: props.narrow ? 116 : 148 }]
    : []),
  {
    title: t('core.games.usage'),
    key: 'usage',
    width: props.game.type.kind === 'client' ? 240 : props.narrow ? 132 : 188,
    ellipsis: true,
  },
  {
    title: t('core.games.actions'),
    key: 'actions',
    width: props.game.type.kind === 'client' ? 190 : props.narrow ? 212 : 256,
  },
])

const tableScroll = computed(() =>
  props.narrow ? { x: props.game.type.kind === 'emulator' ? 676 : 560 } : undefined
)

function statusLabel(device: GameDevice) {
  return statusLabels.value[device.info?.status ?? 10]
}

function isRecoveryPending(uid: string): boolean {
  return Boolean(props.game.runtime.recoveryPending?.includes(uid))
}
</script>

<style scoped>
.target-workspace {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px;
  gap: 14px;
}

.target-workspace--narrow {
  padding: 14px;
}

.detail-banners {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.devices-panel {
  min-width: 0;
  padding: 14px 16px;
}

.target-workspace--narrow .devices-panel {
  padding: 12px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.section-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.device-name {
  font-weight: 500;
  color: var(--ant-color-text);
}

.native-index {
  margin-inline-start: 5px;
  font-size: 12px;
  font-family: var(--font-monospace);
  color: var(--ant-color-text-tertiary);
}

.adb-text {
  font-family: var(--font-monospace);
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.usage-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  color: var(--ant-color-text);
}

.usage-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-primary);
  flex-shrink: 0;
}

.usage-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted-text {
  color: var(--ant-color-text-tertiary);
}
</style>
