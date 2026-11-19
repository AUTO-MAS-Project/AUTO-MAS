<template>
  <div class="tab-content">
    <GameEditor :open="true" :row="game" :types="[]">
      <template #actions>
        <a-button
          v-if="hint('delete')"
          type="link"
          danger
          size="small"
          :disabled="!canRun('delete')"
          @click="remove"
        >
          <template #icon><DeleteOutlined /></template>
          {{ t('core.games.delete') }}
        </a-button>
      </template>
    </GameEditor>

    <section class="devices-panel app-page-section">
      <header class="section-header">
        <h3>{{ t('core.emulator.deviceList') }}</h3>
        <a-space wrap>
          <a-button
            v-if="hint('refresh')"
            size="small"
            :loading="hint('refresh')?.state === 'busy'"
            :disabled="!canRun('refresh')"
            @click="refreshDevices"
          >
            <template #icon><ReloadOutlined /></template>
            {{ t('core.games.refresh') }}
          </a-button>
          <a-dropdown v-if="hint('stable_mode') || hint('capture')">
            <a-button size="small"> {{ t('core.games.more') }} <DownOutlined /> </a-button>
            <template #overlay>
              <a-menu @click="batchAction">
                <a-menu-item
                  v-if="hint('stable_mode')"
                  key="stable_mode"
                  :disabled="!canRun('stable_mode')"
                  >{{ t('core.games.applyStableMode') }}</a-menu-item
                >
                <a-menu-item v-if="hint('capture')" key="capture" :disabled="!canRun('capture')">{{
                  t('core.games.capture')
                }}</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <a-button
            v-if="hint('create_instance')"
            size="small"
            :disabled="!canRun('create_instance')"
            :loading="hint('create_instance')?.state === 'busy'"
            @click="creating = true"
          >
            <template #icon><PlusOutlined /></template>
            {{
              t(
                game.type.type === 'general_emulator'
                  ? 'core.games.addConnection'
                  : 'core.games.createInstance'
              )
            }}
          </a-button>
        </a-space>
      </header>
      <a-alert
        v-if="game.runtime.recoveryPending?.length"
        type="warning"
        :message="t('core.games.recoveryHint')"
        show-icon
        class="recovery-alert"
      />
      <a-table
        :columns="deviceColumns"
        :data-source="devices"
        row-key="uid"
        :pagination="false"
        :scroll="{ x: game.type.kind === 'emulator' ? 640 : 520 }"
        size="small"
      >
        <template #emptyText><a-empty :description="t('core.emulator.noDevice')" /></template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            {{ record.document.info?.name }}
            <span
              v-if="record.document.info && 'index' in record.document.info"
              class="native-index"
            >
              #{{ record.document.info.index }}
            </span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="statusColor(record.document)">{{ statusLabel(record.document) }}</a-tag>
            <a-tag v-if="isDeletedDevice(record.document)">{{ t('core.games.deleted') }}</a-tag>
          </template>
          <template v-else-if="column.key === 'adb'">
            {{ record.document.info?.adb_address || '—' }}
          </template>
          <template v-else-if="column.key === 'usage'">{{
            game.runtime.deviceUsage?.[record.uid] || '—'
          }}</template>
          <template v-else-if="column.key === 'actions'">
            <DeviceActions
              :game="game"
              :device="record"
              @edit="kind => (deviceEditing = { device: record, kind })"
            />
          </template>
        </template>
      </a-table>
    </section>
    <section
      v-if="hint('check_components') || hint('check_update') || hint('update')"
      class="devices-panel app-page-section"
    >
      <ModAvdMaintenance :game="game" />
    </section>

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
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal, message } from 'ant-design-vue'
import { DeleteOutlined, DownOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { Service, type DeviceStatus } from '@/api'
import type { GameDevice, GameDeviceRow, GameRow } from '@/types/games'
import { gameActionHint, gameDevices, isDeletedDevice } from '@/types/games'
import { useGamesApi } from '@/composables/useGamesApi'
import { useGameTriggers } from '@/composables/useGameTriggers'
import CreateInstance from './CreateInstance.vue'
import DeviceActions from './DeviceActions.vue'
import DeviceSettings from './DeviceSettings.vue'
import GameEditor from './GameEditor.vue'
import ModAvdMaintenance from './ModAvdMaintenance.vue'

const props = defineProps<{ game: GameRow }>()
const { t } = useI18n()
const api = useGamesApi()
const operations = useGameTriggers()
const creating = ref(false)
const hint = (field: string) => gameActionHint(props.game, props.game.uid, field)
const canRun = (field: string) => hint(field)?.editable === true
const deviceEditing = ref<{ device: GameDeviceRow; kind: 'settings' | 'connection' | 'options' }>()
const devices = computed(() => gameDevices(props.game))
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
  { title: t('core.games.device'), key: 'name' },
  { title: t('core.games.status'), key: 'status', width: 130 },
  ...(props.game.type.kind === 'emulator'
    ? [{ title: t('core.emulator.colAdb'), key: 'adb', width: 140 }]
    : []),
  { title: t('core.games.usage'), key: 'usage', width: 140 },
  { title: t('core.games.actions'), key: 'actions', width: 190 },
])
function statusLabel(device: GameDevice) {
  return statusLabels.value[device.info?.status ?? 10]
}
function statusColor(device: GameDevice) {
  const status = device.info?.status ?? 10
  if (status === 0) return 'success'
  if ([4, 7].includes(status)) return 'error'
  return [2, 3, 6].includes(status) ? 'processing' : 'default'
}
async function refreshDevices() {
  if (!canRun('refresh')) return
  try {
    await operations.run(props.game, props.game.uid, 'refresh')
  } catch (error) {
    message.error(String(error))
  }
}
function remove() {
  if (!canRun('delete')) return
  Modal.confirm({
    title: t('core.games.deleteConfirm'),
    content: props.game.document.info?.name,
    onOk: async () => {
      if (canRun('delete'))
        await api.remove(props.game).catch(error => message.error(String(error)))
    },
  })
}
function batchAction({ key }: { key: string | number }) {
  if ((key !== 'stable_mode' && key !== 'capture') || !canRun(key)) return
  const stable = key === 'stable_mode'
  const game = props.game
  Modal.confirm({
    title: t(stable ? 'core.games.applyStableMode' : 'core.games.capture'),
    onOk: async () => {
      if (!canRun(key)) return
      try {
        const result = await api.change(game.type.type, stable ? 'stable_mode' : 'capture', () =>
          stable
            ? Service.applyStableModeApiGamesStableModeApplyPost({ gameId: game.uid })
            : Service.captureBaselinesApiGamesGuardCapturePost({ gameId: game.uid })
        )
        const values = Object.values(result.data ?? {}) as unknown[]
        const failures = values.filter(
          item => typeof item === 'object' && item !== null && 'ok' in item && item.ok === false
        ).length
        if (failures)
          message.warning(
            t('core.games.partialSettings', { failed: failures, total: values.length })
          )
      } catch (error) {
        message.error(String(error))
      }
    },
  })
}
</script>

<style scoped>
.tab-content {
  display: flex;
  flex-direction: column;
  gap: var(--app-page-content-gap);
}

.devices-panel {
  min-width: 0;
  padding: var(--app-page-content-padding);
}

.section-header {
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
  border-bottom-width: 1px;
}

.section-header h3 {
  font-size: var(--app-page-card-title-size);
  font-weight: var(--app-page-card-title-weight);
  line-height: var(--app-page-card-title-line-height);
}

.recovery-alert {
  margin-bottom: 12px;
}

.native-index {
  color: var(--ant-color-text-secondary);
}
</style>
