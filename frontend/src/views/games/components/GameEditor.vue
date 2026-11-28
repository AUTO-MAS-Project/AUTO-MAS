<template>
  <section
    v-if="row"
    class="config-section app-page-section"
    :class="{ 'config-section--collapsed': !expanded }"
  >
    <header class="config-header" @click="toggleExpanded">
      <div class="config-header-title">
        <span class="collapse-chevron" aria-hidden="true">
          <DownOutlined v-if="expanded" />
          <RightOutlined v-else />
        </span>
        <h3>{{ t('core.edit.gameConfiguration') }}</h3>
        <span v-if="configSummary" class="config-summary">{{ configSummary }}</span>
      </div>
      <a-space wrap @click.stop>
        <StatusChip v-if="locked" tone="processing">{{ t('core.games.inUse') }}</StatusChip>
        <a-button v-if="dirty" :disabled="saving" @click="resetDraft">
          {{ t('core.emulator.cancel') }}
        </a-button>
        <a-button v-if="dirty" type="primary" :disabled="locked" :loading="saving" @click="save">
          {{ t('core.emulator2.save') }}
        </a-button>
        <a-button @click="toggleExpanded">
          {{ t(expanded ? 'core.games.collapseEdit' : 'core.games.expandEdit') }}
        </a-button>
      </a-space>
    </header>

    <a-config-provider v-if="expanded" :component-disabled="locked || saving">
      <div class="config-form-body">
        <GameConfigFormFields
          :draft="draft"
          :selected-type="selectedType"
          :client-type="clientType"
          :types="types"
          :guard-supported="guardSupported"
          two-column
          @pick-path="pickPath"
        />
      </div>
    </a-config-provider>
  </section>

  <AppModal
    v-else
    :open="open"
    size="md"
    :title="t('core.games.add')"
    :submitting="saving"
    :dirty="dirty"
    :dirty-title="t('core.games.discard')"
    dirty-description=""
    :mask-closable="false"
    @ok="save"
    @cancel="emit('close')"
  >
    <a-config-provider :component-disabled="saving">
      <GameConfigFormFields
        :draft="draft"
        :selected-type="selectedType"
        :client-type="clientType"
        :types="types"
        show-adapter-select
        creating
        @update:selected-type="value => (selectedType = value)"
        @pick-path="pickPath"
      />
    </a-config-provider>
  </AppModal>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { DownOutlined, RightOutlined } from '@ant-design/icons-vue'
import { AppModal, StatusChip } from '@/components/ui'
import { GameCreateIn, type GameTypeItem, type GameUpdateIn } from '@/api'
import { gameActionHint, type GameRow } from '@/types/games'
import { useGamesApi } from '@/composables/useGamesApi'
import { formatTargetConfigSummary, supportsConfigGuard } from '../gamePresentation'
import GameConfigFormFields, { type GameConfigDraft } from './GameConfigFormFields.vue'

const props = defineProps<{ open: boolean; row?: GameRow; types: GameTypeItem[] }>()
const emit = defineEmits<{
  close: []
  created: [uid: string]
  dirtyChange: [uid: string, dirty: boolean]
}>()
const { t } = useI18n()
const api = useGamesApi()
const selectedType = ref('')
const saving = ref(false)
const initial = ref('')
const expanded = ref(false)
const draft = reactive<GameConfigDraft>({
  name: '',
  path: '',
  launcher: '',
  cwd: '',
  adb: '',
  arguments: '',
  waitTime: 300,
  concurrent: false,
  stable: false,
  guard: false,
  forceBefore: false,
  forceClose: false,
  launchWithLauncher: true,
})

const clientType = computed(
  () =>
    (props.row?.type ?? props.types.find(item => item.type === selectedType.value))?.kind ===
    'client'
)
const locked = computed(
  () => !!props.row && gameActionHint(props.row, props.row.uid, 'save')?.editable !== true
)
const guardSupported = computed(() => !!props.row && supportsConfigGuard(props.row))
const configSummary = computed(() => (props.row ? formatTargetConfigSummary(props.row, t) : ''))
const snapshot = () => JSON.stringify({ type: selectedType.value, draft })
const dirty = computed(() => initial.value !== snapshot())

function toggleExpanded() {
  expanded.value = !expanded.value
}

function resetDraft() {
  const info = props.row?.document.info
  selectedType.value = props.row?.type.type ?? props.types[0]?.type ?? ''
  Object.assign(draft, {
    name: info?.name ?? '',
    path: info?.path ?? '',
    launcher: '',
    cwd: '',
    adb: '',
    arguments: '',
    waitTime: 300,
    concurrent: info && 'concurrent_execution' in info ? !!info.concurrent_execution : false,
    stable: false,
    guard: false,
    forceBefore: false,
    forceClose: false,
    launchWithLauncher: true,
  })
  if (selectedType.value === 'avd')
    draft.path = draft.path.replace(/[\\/]sdk[\\/]emulator[\\/]emulator\.exe$/i, '')
  if (info && 'wait_time' in info)
    Object.assign(draft, {
      waitTime: info.wait_time ?? 60,
      launcher: info.launch_path ?? '',
      cwd: info.working_directory ?? '',
      arguments: (info.arguments ?? []).join('\n'),
      forceClose: !!info.force_kill,
      launchWithLauncher: info.launch_with_launcher !== false,
    })
  if (info && 'max_wait_time' in info) draft.waitTime = info.max_wait_time ?? 300
  if (info && 'stable_mode' in info)
    Object.assign(draft, {
      waitTime: info.max_wait_time ?? 300,
      stable: !!info.stable_mode,
      guard: !!info.config_guard,
      forceBefore: !!info.force_kill_before_launch,
      forceClose: !!info.force_kill_on_close,
    })
  if (info && 'adb_path' in info) draft.adb = info.adb_path ?? ''
  initial.value = snapshot()
}

watch(
  () => [props.open, props.row?.uid] as const,
  ([open]) => {
    if (open) {
      resetDraft()
      expanded.value = false
    }
  },
  { immediate: true }
)
watch(
  () => props.row?.document.info,
  () => {
    if (props.open && !dirty.value) resetDraft()
  }
)
watch(
  dirty,
  value => {
    if (props.row) emit('dirtyChange', props.row.uid, value)
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  if (props.row) emit('dirtyChange', props.row.uid, false)
})

async function pickPath(field: 'path' | 'launcher' | 'cwd' | 'adb') {
  try {
    if (field === 'cwd' || (field === 'path' && selectedType.value === 'avd')) {
      const path = await window.electronAPI.selectFolder()
      if (path) draft[field] = path
    } else {
      const paths = await window.electronAPI.selectFile([
        { name: t('core.games.executable'), extensions: ['exe'] },
      ])
      if (paths?.[0]) draft[field] = paths[0]
    }
  } catch (error) {
    message.error(String(error))
  }
}

function payload(): GameUpdateIn['data'] {
  const common = {
    name: draft.name.trim(),
    path: draft.path
      ? selectedType.value === 'avd'
        ? draft.path.replace(/[\\/]+$/, '') + '/sdk/emulator/emulator.exe'
        : draft.path
      : null,
    concurrent_execution: draft.concurrent,
  }
  if (clientType.value)
    return {
      info: {
        ...common,
        launch_path: draft.launcher || null,
        launch_with_launcher: draft.launchWithLauncher,
        working_directory: draft.cwd || null,
        arguments: draft.arguments.split('\n').filter(Boolean),
        wait_time: draft.waitTime,
        force_kill: draft.forceClose,
      },
    }
  if (selectedType.value === 'general_emulator')
    return { info: { ...common, max_wait_time: draft.waitTime, adb_path: draft.adb || null } }
  return {
    info: {
      ...common,
      max_wait_time: draft.waitTime,
      stable_mode: draft.stable,
      config_guard: draft.guard,
      force_kill_before_launch: draft.forceBefore,
      force_kill_on_close: draft.forceClose,
    },
  }
}

async function save() {
  if (locked.value || saving.value || (props.row && !dirty.value)) return
  if (
    !draft.name.trim() ||
    !selectedType.value ||
    (!draft.path && selectedType.value !== 'general_emulator')
  ) {
    message.warning(t('core.games.required'))
    return
  }
  saving.value = true
  try {
    if (props.row) {
      await api.update(props.row, payload())
      await nextTick()
      resetDraft()
    } else {
      const result = await api.create({
        type: selectedType.value as GameCreateIn.type,
        data: payload(),
      })
      const uid = result.order?.[0]?.uid
      if (uid) emit('created', uid)
      emit('close')
    }
  } catch (error) {
    message.error(String(error))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.config-section {
  padding: 14px 16px;
}

.config-section--collapsed {
  padding: 11px 16px;
}

.config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.config-header-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.collapse-chevron {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  color: var(--ant-color-text-secondary);
}

.config-header-title h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.config-summary {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.config-form-body {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--ant-color-border-secondary);
}
</style>
