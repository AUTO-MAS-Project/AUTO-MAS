<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { PowerSignal } from '@/api'
import { useI18n } from 'vue-i18n'
import { fetchTaskTargets, type TaskTarget } from '@/composables/useTaskOptions'
import { getConfig, saveConfig } from '@/utils/config'
import {
  MAX_DESKTOP_SESSION_TARGETS,
  type DesktopSessionRequest,
} from '../../../electron/services/desktopSessionProtocol'

const { t } = useI18n()
const selected = ref<string[]>([])
const targets = ref<TaskTarget[]>([])
const options = computed(() => {
  const atLimit = selected.value.length >= MAX_DESKTOP_SESSION_TARGETS
  const selection = new Set(selected.value)
  return targets.value.map(target => {
    const hasPowerAction = Boolean(
      target.afterAccomplish && target.afterAccomplish !== PowerSignal.NO_ACTION
    )
    const label = `${t(`core.scheduler.scope.${target.kind}`)} · ${target.name}`
    return {
      value: target.value,
      disabled: (hasPowerAction || atLimit) && !selection.has(target.value),
      label: hasPowerAction ? `${label} · ${t('bootstrap.desktopSession.powerAction')}` : label,
    }
  })
})
const loading = ref(false)
const initializing = ref(true)
const starting = ref(false)
const mode = ref<DesktopSessionRequest['mode']>('proxy')
const resolution = ref<DesktopSessionRequest['resolution']>('1080p')

async function loadQueues() {
  loading.value = true
  try {
    targets.value = await fetchTaskTargets()
    selected.value = selected.value.filter(id => options.value.some(item => item.value === id))
  } catch {
    message.error(t('bootstrap.desktopSession.loadTasksFailed'))
  } finally {
    loading.value = false
  }
}

function saveSelection(ids: string[]) {
  selected.value = ids
  // saveConfig 内部已按提交顺序串行落盘，这里不必再排一次队。
  void saveConfig({ desktopSessionQueueIds: ids }).catch(() => {
    message.error(t('bootstrap.desktopSession.saveFailed'))
  })
}

async function open() {
  const launch = window.electronAPI?.desktopSessionOpen
  if (!launch) return
  starting.value = true
  try {
    await launch({ queueIds: [...selected.value], mode: mode.value, resolution: resolution.value })
  } catch {
    message.error(t('bootstrap.desktopSession.openFailed'))
  } finally {
    starting.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const saved = (await getConfig()).desktopSessionQueueIds
    if (Array.isArray(saved)) selected.value = saved.filter(id => typeof id === 'string')
  } catch {
    message.warning(t('bootstrap.desktopSession.loadSelectionFailed'))
  }
  await loadQueues()
  initializing.value = false
})
</script>

<template>
  <a-card :title="t('bootstrap.desktopSession.title')" class="settings-card">
    <a-flex vertical gap="middle">
      <a-select
        :value="selected"
        :options="options"
        :loading="loading"
        :disabled="starting || initializing"
        mode="multiple"
        option-filter-prop="label"
        :placeholder="t('bootstrap.desktopSession.selectTasks')"
        @dropdown-visible-change="(visible: boolean) => visible && !loading && loadQueues()"
        @change="saveSelection"
      />
      <a-space wrap>
        <a-select
          v-model:value="resolution"
          :aria-label="t('bootstrap.desktopSession.resolution')"
          :options="[
            { value: '1080p', label: '1920 × 1080' },
            { value: 'primary', label: t('bootstrap.desktopSession.primaryResolution') },
          ]"
        />
        <a-select
          v-model:value="mode"
          :aria-label="t('bootstrap.desktopSession.minimizeMode')"
          :options="[
            { value: 'proxy', label: t('bootstrap.desktopSession.proxy') },
            { value: 'native', label: t('bootstrap.desktopSession.native') },
          ]"
        />
      </a-space>
      <a-flex justify="space-between" align="center" gap="middle">
        <a-typography-text type="secondary">{{
          t('bootstrap.desktopSession.emptySelection')
        }}</a-typography-text>
        <a-button
          type="primary"
          :loading="starting"
          :disabled="loading || selected.length > MAX_DESKTOP_SESSION_TARGETS"
          @click="open"
        >
          {{
            selected.length
              ? t('bootstrap.desktopSession.openWithTasks')
              : t('bootstrap.desktopSession.open')
          }}
        </a-button>
      </a-flex>
    </a-flex>
  </a-card>
</template>
