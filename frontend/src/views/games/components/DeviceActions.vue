<template>
  <a-space>
    <a-button
      v-for="action in primaryActions.filter(shown)"
      :key="action"
      type="link"
      size="small"
      :aria-label="label(action)"
      :loading="running(action)"
      :disabled="!canRun(action)"
      @click="operate(action)"
      >{{ label(action) }}</a-button
    >
    <a-dropdown v-if="moreActions.length">
      <a-button type="link" size="small" :loading="!!runningMenuAction"
        >{{ runningMenuAction ? label(runningMenuAction) : t('core.games.more') }} <DownOutlined
      /></a-button>
      <template #overlay>
        <a-menu @click="menuAction">
          <a-menu-item
            v-for="action in moreActions"
            :key="action"
            :danger="action === 'delete_instance'"
            :disabled="!canRun(action)"
          >
            <LoadingOutlined v-if="running(action)" />
            {{ label(action) }}
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>
  </a-space>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal, message } from 'ant-design-vue'
import { DownOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import type { GameRow, GameDeviceRow } from '@/types/games'
import { gameActionHint } from '@/types/games'
import { useGameTriggers } from '@/composables/useGameTriggers'
import { useGamesApi } from '@/composables/useGamesApi'

const props = defineProps<{ game: GameRow; device: GameDeviceRow }>()
const emit = defineEmits<{ edit: [kind: 'settings' | 'connection' | 'options'] }>()
const { t } = useI18n()
const operations = useGameTriggers()
const api = useGamesApi()
const primaryActions = ['open', 'close', 'show'] as const
const instanceActions = [
  'hide',
  'minimize',
  'maximize',
  'open_store',
  'install_app',
  'delete_instance',
] as const
const editActions = ['settings', 'connection', 'options'] as const
type InstanceAction = (typeof primaryActions)[number] | (typeof instanceActions)[number]
type EditAction = (typeof editActions)[number]
type Action = InstanceAction | EditAction

const moreActions = computed(() => [...instanceActions, ...editActions].filter(shown))
const runningMenuAction = computed(() => instanceActions.find(running))

function hint(action: Action) {
  return gameActionHint(props.game, props.device.uid, action)
}
function running(action: Action) {
  return hint(action)?.state === 'busy'
}
function label(action: Action) {
  const key = {
    install_app: 'installApp',
    delete_instance: 'deleteInstance',
    options: 'instanceOptions',
  }
  return t(`core.games.${action in key ? key[action as keyof typeof key] : action}`)
}
function shown(action: Action) {
  return hint(action) !== undefined
}
function canRun(action: Action) {
  return hint(action)?.editable === true
}

async function operate(action: InstanceAction) {
  if (!canRun(action)) return
  try {
    await operations.run(props.game, props.device.uid, action)
  } catch (error) {
    message.error(String(error))
  }
}
async function install() {
  if (!canRun('install_app')) return
  try {
    const paths = await window.electronAPI.selectFile([{ name: 'APK', extensions: ['apk'] }])
    if (!paths?.[0] || !canRun('install_app')) return
    await api.updateDevice(props.game, props.device.uid, { installation: { path: paths[0] } })
    await operate('install_app')
  } catch (error) {
    message.error(String(error))
  }
}
function menuAction({ key }: { key: string | number }) {
  const action = moreActions.value.find(action => action === key)
  if (!action || !canRun(action)) return
  if (action === 'settings' || action === 'connection' || action === 'options') {
    emit('edit', action)
    return
  }
  if (action === 'install_app') {
    void install()
    return
  }
  if (action === 'delete_instance') {
    Modal.confirm({
      title: t('core.games.deleteInstanceConfirm'),
      content: props.device.document.info?.name,
      onOk: () => operate('delete_instance'),
    })
    return
  }
  void operate(action)
}
</script>
