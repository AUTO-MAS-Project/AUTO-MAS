<template>
  <a-space v-if="visiblePrimaryActions.length || moreActions.length" :size="6" wrap>
    <a-button
      v-for="action in visiblePrimaryActions"
      :key="action"
      :type="action === 'open' ? 'primary' : 'default'"
      :ghost="action === 'open'"
      :danger="action === 'close'"
      size="middle"
      class="row-action-btn"
      :class="{ 'row-action-btn--narrow': narrow }"
      :aria-label="label(action)"
      :loading="running(action)"
      :disabled="!canRun(action)"
      @click="operate(action)"
    >
      <template #icon>
        <PlayCircleOutlined v-if="action === 'open'" />
        <PoweroffOutlined v-else-if="action === 'close'" />
        <EyeOutlined v-else />
      </template>
      {{ label(action) }}
    </a-button>

    <a-dropdown v-if="moreActions.length">
      <a-button
        size="middle"
        class="row-action-btn"
        :class="{ 'row-action-btn--narrow': narrow }"
        :aria-label="narrow ? t('core.games.more') : undefined"
        :loading="!!runningMenuAction"
      >
        <template v-if="narrow && !runningMenuAction">
          <DownOutlined />
        </template>
        <template v-else>
          {{ runningMenuAction ? label(runningMenuAction) : t('core.games.more') }}
          <DownOutlined />
        </template>
      </a-button>
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
  <span v-else class="no-action-placeholder">—</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useConfirm } from '@/composables/useConfirm'
import {
  DownOutlined,
  EyeOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  PoweroffOutlined,
} from '@ant-design/icons-vue'
import type { GameRow, GameDeviceRow } from '@/types/games'
import { gameActionHint } from '@/types/games'
import { useGameTriggers } from '@/composables/useGameTriggers'
import { useGamesApi } from '@/composables/useGamesApi'

const props = withDefaults(
  defineProps<{ game: GameRow; device: GameDeviceRow; narrow?: boolean }>(),
  { narrow: false }
)
const emit = defineEmits<{ edit: [kind: 'settings' | 'connection' | 'options'] }>()
const { t } = useI18n()
const { confirm } = useConfirm()
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

const visiblePrimaryActions = computed(() => primaryActions.filter(shown))
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
    void confirm({
      tone: 'danger',
      title: t('core.games.deleteInstanceConfirm'),
      description: props.device.document.info?.name ?? undefined,
      onOk: () => operate('delete_instance'),
    })
    return
  }
  void operate(action)
}
</script>

<style scoped>
.row-action-btn {
  padding-inline: 10px;
}

.row-action-btn--narrow {
  padding-inline: 7px;
}

.no-action-placeholder {
  color: var(--ant-color-text-tertiary);
}
</style>
