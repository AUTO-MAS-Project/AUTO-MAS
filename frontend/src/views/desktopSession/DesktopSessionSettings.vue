<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { GetService, PowerSignal } from '@/api'
import { translate as t } from '@/i18n'
import { getConfig, saveConfig } from '@/utils/config'
import type { DesktopSessionRequest } from '../../../electron/services/desktopSessionProtocol'

const selected = ref<string[]>([])
const options = ref<{ value: string; label: string; disabled: boolean }[]>([])
const loading = ref(false)
const starting = ref(false)
const mode = ref<DesktopSessionRequest['mode']>('proxy')
const resolution = ref<DesktopSessionRequest['resolution']>('1080p')
const supported = Boolean(window.electronAPI?.desktopSessionOpen)
let saves = Promise.resolve<unknown>(undefined)

async function loadQueues() {
  loading.value = true
  try {
    const [queues, scripts] = await Promise.all([
      GetService.getQueuesApiQueueGetPost({}),
      GetService.getScriptApiScriptsGetPost({}),
    ])
    if (queues.code !== 200) throw new Error(queues.message)
    if (scripts.code !== 200) throw new Error(scripts.message)
    options.value = queues.index.map(({ uid }) => {
      const info = queues.data[uid]?.Info
      const disabled = Boolean(
        info?.AfterAccomplish && info.AfterAccomplish !== PowerSignal.NO_ACTION
      )
      const label = `${t('core.scheduler.scope.queue')} · ${info?.Name || uid}`
      return {
        value: uid,
        disabled,
        label: disabled ? `${label}（请将完成后操作设为无操作）` : label,
      }
    })
    options.value.push(
      ...scripts.index.map(({ uid }) => ({
        value: uid,
        disabled: false,
        label: `${t('core.scheduler.scope.script')} · ${scripts.data[uid]?.Info?.Name || uid}`,
      }))
    )
    selected.value = selected.value.filter(id => options.value.some(item => item.value === id))
  } catch {
    message.error('读取桌面分身任务失败，请重试。')
  } finally {
    loading.value = false
  }
}

function saveSelection(ids: string[]) {
  selected.value = ids
  saves = saves
    .then(() => saveConfig({ desktopSessionQueueIds: ids }))
    .catch(() => {
      message.error('保存桌面分身队列选择失败。')
    })
}

async function open() {
  const launch = window.electronAPI?.desktopSessionOpen
  if (!launch) return
  starting.value = true
  try {
    await launch({ queueIds: [...selected.value], mode: mode.value, resolution: resolution.value })
  } catch (error) {
    message.error(error instanceof Error ? error.message : '无法打开桌面分身。')
  } finally {
    starting.value = false
  }
}

onMounted(async () => {
  if (!supported) return
  try {
    const saved = (await getConfig()).desktopSessionQueueIds
    if (Array.isArray(saved)) selected.value = saved.filter(id => typeof id === 'string')
  } catch {
    message.warning('无法读取已保存的分身队列选择。')
  }
  await loadQueues()
})
</script>

<template>
  <a-card title="桌面分身" class="settings-card">
    <a-flex vertical gap="middle">
      <a-alert type="warning" show-icon message="风险提示：该功能为实验功能" />
      <a-alert v-if="!supported" type="info" message="请在 Windows x64 桌面版中打开此功能。" />
      <template v-else>
        <a-select
          :value="selected"
          :options="options"
          :loading="loading"
          :disabled="starting"
          mode="multiple"
          option-filter-prop="label"
          placeholder="选择要在桌面分身运行的队列或托管任务"
          @dropdown-visible-change="(visible: boolean) => visible && !loading && loadQueues()"
          @change="saveSelection"
        />
        <a-space wrap>
          <a-select
            v-model:value="resolution"
            aria-label="分身分辨率"
            :options="[
              { value: '1080p', label: '1920 × 1080' },
              { value: 'primary', label: '同步主屏分辨率' },
            ]"
          />
          <a-select
            v-model:value="mode"
            aria-label="最小化模式"
            :options="[
              { value: 'proxy', label: '后台最小化' },
              { value: 'native', label: '原生最小化' },
            ]"
          />
        </a-space>
        <a-flex justify="space-between" align="center" gap="middle">
          <a-typography-text type="secondary">留空时只打开分身桌面。</a-typography-text>
          <a-button type="primary" :loading="starting" :disabled="loading" @click="open">
            {{ selected.length ? '打开分身并启动任务' : '打开桌面分身' }}
          </a-button>
        </a-flex>
      </template>
    </a-flex>
  </a-card>
</template>
