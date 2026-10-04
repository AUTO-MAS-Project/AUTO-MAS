<script setup lang="ts">
/**
 * 魔改 AVD 组件的下载区：所需空间、下载源与测速、轻量桌面、许可协议全文与同意、下载进度。
 * 开始 / 取消下载的按钮在外层弹窗底部，测速也由外层做；这里只收集选择、显示进度。
 */
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { ThunderboltOutlined } from '@ant-design/icons-vue'

import type { Emulator2AvdSourceItem } from '@/api'
import type { WSEmulator2AvdInstallProgressData } from '@/services/websocket/types'
import { formatBytes, formatSpeed } from '@/utils/byteFormat'
import { jobPercent } from '../avdLogic'

const sourceId = defineModel<string | null>('sourceId', { required: true })
const includeLauncher = defineModel<boolean>('includeLauncher', { required: true })
const agreed = defineModel<boolean>('agreed', { required: true })
const props = defineProps<{
  requiredDiskBytes?: number
  freeDiskBytes?: number | null
  licenseText: string
  licenseLoading: boolean
  job: WSEmulator2AvdInstallProgressData | null
  running: boolean
  /** 测速结果与测速中：放在外层，下载区重新出现时不丢 */
  sources: Emulator2AvdSourceItem[]
  probing: boolean
}>()
defineEmits<{ probe: [] }>()

const { t } = useI18n()

const percent = computed(() => jobPercent(props.job))

const sourceOptions = computed(() => [
  { value: null, label: t('emulator2.avd.sourceAuto') },
  ...props.sources.map(item => ({
    value: item.id,
    label: item.ok
      ? `${item.name} · ${formatSpeed(item.speedBytesPerSec ?? 0)}`
      : `${item.name} · ${t('emulator2.avd.sourceDown')}`,
    disabled: !item.ok,
  })),
])

const stageText = (stage: string) => {
  const key = `emulator2.avd.stage.${stage}`
  const text = t(key)
  return text === key ? stage : text
}
</script>

<template>
  <div class="download-block">
    <p v-if="requiredDiskBytes" class="disk-line">
      {{
        t('emulator2.avd.diskNeed', {
          need: formatBytes(requiredDiskBytes),
          free:
            freeDiskBytes === null || freeDiskBytes === undefined
              ? '—'
              : formatBytes(freeDiskBytes),
        })
      }}
    </p>

    <template v-if="!running">
      <a-form layout="vertical">
        <a-form-item :label="t('emulator2.avd.source')">
          <div class="source-row">
            <a-select v-model:value="sourceId" :options="sourceOptions" style="flex: 1" />
            <a-button :icon="h(ThunderboltOutlined)" :loading="probing" @click="$emit('probe')">
              {{ t('emulator2.avd.probe') }}
            </a-button>
          </div>
        </a-form-item>
        <a-form-item>
          <a-checkbox v-model:checked="includeLauncher">
            {{ t('emulator2.avd.includeLauncher') }}
          </a-checkbox>
        </a-form-item>
        <a-form-item :label="t('emulator2.avd.license')">
          <a-spin :spinning="licenseLoading">
            <pre class="license-text">{{ licenseText }}</pre>
          </a-spin>
          <a-checkbox v-model:checked="agreed" :disabled="!licenseText" class="agree">
            {{ t('emulator2.avd.licenseAgree') }}
          </a-checkbox>
        </a-form-item>
      </a-form>
    </template>

    <div v-if="job" class="progress-block">
      <div class="progress-head">
        <span>
          {{ stageText(job.stage) }}
          <template v-if="job.componentName && running">
            ·
            {{
              t('emulator2.avd.progressComponent', {
                name: job.componentName,
                index: job.componentIndex,
                count: job.componentCount,
              })
            }}
          </template>
        </span>
        <span v-if="running && job.stage === 'downloading'" class="progress-meta">
          {{ formatBytes(job.downloadedBytes ?? 0) }} / {{ formatBytes(job.totalBytes ?? 0) }}
          <template v-if="job.speedBytesPerSec">
            · {{ formatSpeed(job.speedBytesPerSec) }}</template
          >
        </span>
      </div>
      <a-progress
        v-if="percent !== null"
        :percent="percent"
        :status="
          job.status === 'failed' ? 'exception' : job.status === 'success' ? 'success' : 'active'
        "
      />
      <a-alert
        v-if="job.status === 'failed' && job.error"
        type="error"
        show-icon
        :message="job.error"
      />
    </div>
  </div>
</template>

<style scoped>
.download-block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.disk-line {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.source-row {
  display: flex;
  gap: 8px;
}

.license-text {
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
  padding: 8px 12px;
  white-space: pre-wrap;
  font-size: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.agree {
  margin-top: 8px;
}

.progress-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.progress-meta {
  color: var(--ant-color-text-tertiary);
}
</style>
