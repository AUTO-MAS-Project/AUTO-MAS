<template>
  <AppModal
    :open="open"
    size="md"
    :title="
      t(
        kind === 'connection'
          ? 'core.games.connection'
          : kind === 'options'
            ? 'core.games.instanceOptions'
            : 'core.games.settings'
      )
    "
    :footer="kind === 'options' ? 'close' : 'confirm'"
    :submitting="saving"
    :ok-disabled="saveBlocked"
    :dirty="dirty"
    :session-key="`${device.uid}:${kind}`"
    :dirty-title="t('core.games.discard')"
    dirty-description=""
    :mask-closable="false"
    @ok="save"
    @cancel="emit('close')"
  >
    <a-spin :spinning="loading">
      <a-alert v-if="error" type="error" :message="error" show-icon />
      <a-form v-if="kind === 'connection'" layout="vertical">
        <a-form-item :label="t('core.games.adbAddress')" required
          ><a-input v-model:value="connection.address"
        /></a-form-item>
        <a-form-item :label="t('core.games.arguments')" :extra="t('core.games.oneArgumentPerLine')"
          ><a-textarea v-model:value="connection.arguments" :rows="4"
        /></a-form-item>
      </a-form>
      <a-descriptions v-else-if="kind === 'options'" :column="1" bordered size="small">
        <a-descriptions-item
          v-for="(value, key) in options"
          :key="key"
          :label="t(`core.games.options.${key}`, String(key))"
          >{{ value }}</a-descriptions-item
        >
      </a-descriptions>
      <a-form v-else layout="vertical">
        <a-row :gutter="16">
          <a-col v-for="field in fields" :key="field.key" :span="12">
            <a-form-item
              :label="t(`core.games.settingsFields.${field.key}`)"
              :extra="t(`core.games.settingStates.${states[field.key] ?? 'unset'}`)"
            >
              <a-input-number
                v-model:value="draft[field.key]"
                :min="field.min"
                :max="field.max"
                :disabled="states[field.key] === 'unreadable'"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-checkbox v-model:checked="batch">{{ t('core.games.applyAll') }}</a-checkbox>
        <a-alert v-if="result" type="info" :message="result" show-icon class="settings-result" />
      </a-form>
    </a-spin>
  </AppModal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { AppModal } from '@/components/ui'
import { Service } from '@/api'
import { gameActionHint, type GameRow, type GameDeviceRow } from '@/types/games'
import { checkedGameResponse, useGamesApi } from '@/composables/useGamesApi'

const props = defineProps<{
  open: boolean
  game: GameRow
  device: GameDeviceRow
  kind: 'settings' | 'connection' | 'options'
}>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const api = useGamesApi()
const saveBlocked = computed(
  () => gameActionHint(props.game, props.device.uid, props.kind)?.editable !== true
)
const fields = [
  { key: 'width', min: 160, max: 4096 },
  { key: 'height', min: 160, max: 4096 },
  { key: 'dpi', min: 80, max: 640 },
  { key: 'cpu', min: 1, max: 64 },
  { key: 'memoryMb', min: 512, max: 65536 },
  { key: 'fps', min: 1, max: 240 },
]
const loading = ref(false),
  saving = ref(false),
  error = ref(''),
  batch = ref(false),
  result = ref('')
const draft = reactive<Record<string, number | null>>({})
const original = ref<Record<string, number | null>>({})
const states = reactive<Record<string, string>>({})
const connection = reactive({ address: '', arguments: '' })
const initialConnection = ref('')
const options = ref<Record<string, unknown>>({})
watch(
  () => [props.open, props.device.uid] as const,
  async ([open]) => {
    if (!open) return
    error.value = ''
    result.value = ''
    batch.value = false
    loading.value = true
    try {
      if (props.kind === 'connection') {
        const info = props.device.document.info
        connection.address = info && 'adb_address' in info ? (info.adb_address ?? '') : ''
        connection.arguments = info && 'arguments' in info ? (info.arguments ?? []).join('\n') : ''
        initialConnection.value = JSON.stringify(connection)
      } else if (props.kind === 'options') {
        options.value =
          checkedGameResponse(
            await Service.deviceOptionsApiGamesDeviceOptionsPost({
              gameId: props.game.uid,
              deviceId: props.device.uid,
            })
          ).data ?? {}
      } else {
        const data =
          checkedGameResponse(
            await Service.gameDeviceSettingsApiGamesSettingsGetPost({
              gameId: props.game.uid,
              deviceId: props.device.uid,
            })
          ).data ?? {}
        for (const field of fields) {
          const item: unknown = data[field.key]
          const value =
            typeof item === 'object' &&
            item !== null &&
            'value' in item &&
            typeof item.value === 'number'
              ? item.value
              : null
          const state =
            typeof item === 'object' &&
            item !== null &&
            'state' in item &&
            typeof item.state === 'string'
              ? item.state
              : 'unreadable'
          draft[field.key] = value
          states[field.key] = ['saved', 'default', 'unset', 'unreadable'].includes(state)
            ? state
            : 'unreadable'
        }
        original.value = { ...draft }
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

function changes() {
  return Object.fromEntries(
    Object.entries(draft).filter(([key, value]) => value !== null && value !== original.value[key])
  ) as Record<string, number>
}
async function save() {
  if (saveBlocked.value) return
  if (props.kind === 'options') {
    emit('close')
    return
  }
  saving.value = true
  error.value = ''
  try {
    if (props.kind === 'connection') {
      await api.updateDevice(props.game, props.device.uid, {
        info: {
          adb_address: connection.address.trim(),
          arguments: connection.arguments.split('\n').filter(Boolean),
        },
      })
    } else {
      const patch = changes()
      if (!Object.keys(patch).length) {
        emit('close')
        return
      }
      if (batch.value) {
        const response = await api.change(props.game.type.type, 'batch_settings', () =>
          Service.batchGameSettingsApiGamesSettingsBatchPost({
            gameId: props.game.uid,
            changes: patch,
          })
        )
        const outcomes = Object.values(response.data ?? {}) as unknown[]
        const failed = outcomes.filter(
          item => typeof item === 'object' && item !== null && 'ok' in item && item.ok === false
        ).length
        if (failed) {
          result.value = t('core.games.partialSettings', { failed, total: outcomes.length })
          return
        }
      } else
        await api.change(props.game.type.type, 'settings', () =>
          Service.updateGameSettingsApiGamesSettingsUpdatePost({
            gameId: props.game.uid,
            deviceId: props.device.uid,
            changes: patch,
            expected: Object.fromEntries(
              Object.keys(patch).map(key => [key, original.value[key] ?? null])
            ),
          })
        )
    }
    emit('close')
  } catch (e) {
    error.value = String(e)
    message.error(String(e))
  } finally {
    saving.value = false
  }
}
const dirty = computed(() =>
  props.kind === 'connection'
    ? initialConnection.value !== JSON.stringify(connection)
    : props.kind === 'settings' && Object.keys(changes()).length > 0
)
</script>

<style scoped>
.settings-result {
  margin-top: 16px;
}
</style>
