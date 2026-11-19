<template>
  <component
    :is="row ? 'section' : AntModal"
    v-bind="row ? { class: 'config-section app-page-section' } : modalProps"
    @ok="save"
    @cancel="close"
  >
    <header v-if="row" class="section-header">
      <h3>{{ t('core.edit.gameConfiguration') }}</h3>
      <a-space wrap>
        <a-tag v-if="locked" color="processing">{{ t('core.games.inUse') }}</a-tag>
        <a-button v-if="dirty" size="small" :disabled="saving" @click="resetDraft">
          {{ t('core.emulator.cancel') }}
        </a-button>
        <a-button
          v-if="dirty"
          type="primary"
          size="small"
          :disabled="locked"
          :loading="saving"
          @click="save"
        >
          {{ t('core.emulator2.save') }}
        </a-button>
        <slot name="actions" />
      </a-space>
    </header>

    <a-config-provider :component-disabled="locked || saving">
      <a-descriptions bordered size="small" :column="row ? 2 : 1" class="config-form">
        <a-descriptions-item :label="t('core.games.name')">
          <a-input
            v-model:value="draft.name"
            :aria-label="t('core.games.name')"
            size="small"
            :bordered="false"
          />
        </a-descriptions-item>
        <a-descriptions-item :label="t('core.games.adapter')">
          <span v-if="row">{{ row.type.name }}</span>
          <a-select
            v-else
            v-model:value="selectedType"
            :options="types.map(item => ({ value: item.type, label: item.name }))"
            :aria-label="t('core.games.adapter')"
            size="small"
            :bordered="false"
            class="adapter-select"
          />
        </a-descriptions-item>
        <a-descriptions-item
          :label="t(selectedType === 'avd' ? 'core.games.installRoot' : 'core.games.executable')"
          :span="row ? 2 : 1"
        >
          <a-input
            v-model:value="draft.path"
            readonly
            size="small"
            :bordered="false"
            :placeholder="t('core.games.selectPath')"
          >
            <template #suffix>
              <a-button
                type="text"
                size="small"
                :aria-label="t('core.games.browse')"
                @click="pickPath('path')"
              >
                <template #icon><FolderOpenOutlined /></template>
              </a-button>
            </template>
          </a-input>
        </a-descriptions-item>
        <a-descriptions-item :label="t('core.games.waitTime')">
          <a-input-number
            v-model:value="draft.waitTime"
            :min="1"
            :max="9999"
            size="small"
            :bordered="false"
          />
        </a-descriptions-item>
        <a-descriptions-item :label="t('core.games.concurrent')">
          <a-switch v-model:checked="draft.concurrent" size="small" />
        </a-descriptions-item>
        <template v-if="clientType">
          <a-descriptions-item :label="t('core.games.launcher')" :span="row ? 2 : 1">
            <a-input
              v-model:value="draft.launcher"
              readonly
              size="small"
              :bordered="false"
              :placeholder="t('core.games.optional')"
            >
              <template #suffix>
                <a-button
                  type="text"
                  size="small"
                  :aria-label="t('core.games.browse')"
                  @click="pickPath('launcher')"
                >
                  <template #icon><FolderOpenOutlined /></template>
                </a-button>
              </template>
            </a-input>
          </a-descriptions-item>
          <a-descriptions-item :label="t('core.games.launchWithLauncher')">
            <a-switch v-model:checked="draft.launchWithLauncher" size="small" />
          </a-descriptions-item>
          <a-descriptions-item :label="t('core.games.forceClose')">
            <a-switch v-model:checked="draft.forceClose" size="small" />
          </a-descriptions-item>
          <a-descriptions-item :label="t('core.games.workingDirectory')" :span="row ? 2 : 1">
            <a-input
              v-model:value="draft.cwd"
              readonly
              size="small"
              :bordered="false"
              :placeholder="t('core.games.optional')"
            >
              <template #suffix>
                <a-button
                  type="text"
                  size="small"
                  :aria-label="t('core.games.browse')"
                  @click="pickPath('cwd')"
                >
                  <template #icon><FolderOpenOutlined /></template>
                </a-button>
              </template>
            </a-input>
          </a-descriptions-item>
          <a-descriptions-item :label="t('core.games.arguments')" :span="row ? 2 : 1">
            <a-textarea
              v-model:value="draft.arguments"
              :placeholder="t('core.games.oneArgumentPerLine')"
              :auto-size="{ minRows: 1, maxRows: 4 }"
              size="small"
              :bordered="false"
            />
          </a-descriptions-item>
        </template>
        <a-descriptions-item
          v-else-if="selectedType === 'general_emulator'"
          :label="t('core.games.adbPath')"
          :span="row ? 2 : 1"
        >
          <a-input
            v-model:value="draft.adb"
            readonly
            size="small"
            :bordered="false"
            :placeholder="t('core.games.optional')"
          >
            <template #suffix>
              <a-button
                type="text"
                size="small"
                :aria-label="t('core.games.browse')"
                @click="pickPath('adb')"
              >
                <template #icon><FolderOpenOutlined /></template>
              </a-button>
            </template>
          </a-input>
        </a-descriptions-item>
        <template v-else-if="selectedType">
          <a-descriptions-item v-if="selectedType !== 'avd'" :label="t('core.games.stableMode')">
            <a-switch v-model:checked="draft.stable" size="small" />
          </a-descriptions-item>
          <a-descriptions-item :label="t('core.games.configGuard')">
            <a-switch v-model:checked="draft.guard" size="small" />
          </a-descriptions-item>
          <a-descriptions-item
            v-if="selectedType === 'mumu'"
            :label="t('core.games.forceBeforeLaunch')"
          >
            <a-switch v-model:checked="draft.forceBefore" size="small" />
          </a-descriptions-item>
          <a-descriptions-item :label="t('core.games.forceClose')">
            <a-switch v-model:checked="draft.forceClose" size="small" />
          </a-descriptions-item>
        </template>
      </a-descriptions>
    </a-config-provider>
  </component>
</template>
<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal as AntModal, message } from 'ant-design-vue'
import { GameCreateIn, type GameTypeItem, type GameUpdateIn } from '@/api'
import { gameActionHint, type GameRow } from '@/types/games'
import { useGamesApi } from '@/composables/useGamesApi'
import { FolderOpenOutlined } from '@ant-design/icons-vue'

const props = defineProps<{ open: boolean; row?: GameRow; types: GameTypeItem[] }>()
const emit = defineEmits<{ close: []; created: [uid: string] }>()
const { t } = useI18n()
const api = useGamesApi()
const selectedType = ref('')
const saving = ref(false)
const initial = ref('')
const draft = reactive({
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
const modalProps = computed(() => ({
  open: props.open,
  title: t('core.games.add'),
  confirmLoading: saving.value,
  maskClosable: false,
}))
const snapshot = () => JSON.stringify({ type: selectedType.value, draft })
const dirty = computed(() => initial.value !== snapshot())

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
  () => props.open,
  open => {
    if (open) resetDraft()
  },
  { immediate: true }
)
watch(
  () => props.row?.document.info,
  () => {
    if (props.open && !dirty.value) resetDraft()
  }
)

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
function close() {
  if (!dirty.value) {
    emit('close')
    return
  }
  AntModal.confirm({ title: t('core.games.discard'), onOk: () => emit('close') })
}
</script>

<style scoped>
.config-section {
  padding: var(--app-page-content-padding);
}

.section-header {
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  border-bottom-width: 1px;
}

.section-header h3 {
  font-size: var(--app-page-card-title-size);
  font-weight: var(--app-page-card-title-weight);
  line-height: var(--app-page-card-title-line-height);
}

.config-form :deep(.ant-descriptions-item-label) {
  white-space: nowrap;
}

.adapter-select {
  min-width: 0;
  width: 100%;
}
</style>
