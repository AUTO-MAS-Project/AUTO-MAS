<script setup lang="ts">
/**
 * 「添加魔改 AVD」时的一键安装：选的是空文件夹时，MAS 从 GitHub 下载最新的魔改 AVD 装进去，再运行包里的
 * 「补全组件」从 Google 官方渠道下载 adb 与系统镜像；已经解压好、只缺组件的目录只补全组件。
 *
 * adb 与系统镜像受《Android SDK 许可协议》约束：开始前先把全文给用户看，勾选同意后才开始。
 * 装好后由父组件重新检查，组件齐了照原来的流程点「添加」。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'

import { useAvdUpdateApi } from '@/composables/useAvdUpdateApi'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_AVD_UPDATE_PROGRESS,
  WS_ID_EMULATOR_MANAGER,
  type WSAvdUpdateProgressData,
} from '@/services/websocket/types'
import { formatBytes, formatSpeed } from '@/utils/byteFormat'
import { samePath } from '../avdLogic'

/** ``hasEmulator``：目录里已经有魔改 AVD（只缺组件），只需补全组件 */
const props = defineProps<{ root: string; hasEmulator: boolean }>()
const emit = defineEmits<{ installed: [] }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const api = useAvdUpdateApi()

/** 没收到 WebSocket 时的兜底轮询间隔（毫秒） */
const POLL_MS = 2000

const licenseOpen = ref(false)
const licenseLoading = ref(false)
const licenseText = ref('')
const licenseSource = ref('')
const agreed = ref(false)
const starting = ref(false)
const busy = ref(false)
const progress = ref<WSAvdUpdateProgressData | null>(null)
let subscription: string | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null

const running = computed(() => (progress.value?.status === 'running' ? progress.value : null))
const failed = computed(() => (progress.value?.status === 'failed' ? progress.value.message : ''))
const detail = computed(() => {
  const item = running.value
  if (!item?.totalBytes) return ''
  const parts = [`${formatBytes(item.downloadedBytes ?? 0)} / ${formatBytes(item.totalBytes)}`]
  if (item.stage === 'downloading' && item.speedBytesPerSec) {
    parts.push(formatSpeed(item.speedBytesPerSec))
  }
  return parts.join(' · ')
})

const describe = (error: unknown) => (error instanceof Error ? error.message : String(error))

const finish = (data: WSAvdUpdateProgressData) => {
  busy.value = false
  if (data.status === 'success') {
    message.success(data.message)
    emit('installed')
  }
}

const poll = async () => {
  pollTimer = null
  try {
    const status = await api.getInstallStatus(props.root)
    busy.value = Boolean(status.busy)
    if (status.progress) {
      progress.value = { root: props.root, ...status.progress } as WSAvdUpdateProgressData
      if (!status.busy && status.progress.status !== 'running') finish(progress.value)
    }
  } catch (error) {
    logger.warn(`读取魔改 AVD 安装进度失败 (${props.root}): ${describe(error)}`)
  }
  if (busy.value) pollTimer = setTimeout(() => void poll(), POLL_MS)
}

const onProgress = (data: WSAvdUpdateProgressData) => {
  if (!samePath(data.root, props.root)) return
  progress.value = data
  if (data.status !== 'running') finish(data)
}

/** 先取许可协议全文给用户看，同意了才开始 */
const openLicense = async () => {
  licenseLoading.value = true
  try {
    const response = await api.getLicense()
    licenseText.value = response.text ?? ''
    licenseSource.value = response.source ?? ''
    agreed.value = false
    licenseOpen.value = true
  } catch (error) {
    message.error(describe(error))
  } finally {
    licenseLoading.value = false
  }
}

const start = async () => {
  if (!agreed.value) return
  starting.value = true
  try {
    const response = await api.startInstall(props.root, true)
    if (!response.ok) {
      message.warning(response.message)
      return
    }
    licenseOpen.value = false
    busy.value = true
    progress.value = null
    void poll()
  } catch (error) {
    logger.error(`安装魔改 AVD 失败 (${props.root}): ${describe(error)}`)
    message.error(describe(error))
  } finally {
    starting.value = false
  }
}

const cancel = async () => {
  try {
    const response = await api.cancel(props.root)
    if (!response.ok) message.warning(response.message)
  } catch (error) {
    message.error(describe(error))
  }
}

watch(
  () => props.root,
  () => {
    progress.value = null
    void poll()
  }
)

onMounted(() => {
  subscription = subscribe({ id: WS_ID_EMULATOR_MANAGER, type: WS_AVD_UPDATE_PROGRESS }, envelope =>
    onProgress(envelope.data)
  )
  void poll()
})

onBeforeUnmount(() => {
  if (subscription) unsubscribe(subscription)
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <section class="avd-first-install">
    <h4 class="block-title">{{ t('emulator2.avd.install.title') }}</h4>
    <div class="install-hint">
      {{
        hasEmulator ? t('emulator2.avd.install.componentsHint') : t('emulator2.avd.install.hint')
      }}
    </div>
    <div v-if="running" class="install-progress">
      <div class="progress-text">
        <span class="progress-message">{{ running.message }}</span>
        <span class="progress-detail">{{ detail }}</span>
      </div>
      <a-progress
        :percent="Math.round(running.percent ?? 0)"
        :status="running.percent == null ? 'active' : 'normal'"
        :show-info="running.percent != null"
        size="small"
      />
      <a-button
        v-if="['downloading', 'extracting', 'verifying'].includes(running.stage)"
        size="small"
        @click="cancel"
      >
        {{ t('emulator2.avd.update.cancel') }}
      </a-button>
    </div>
    <a-alert v-else-if="failed" type="error" show-icon :message="failed" />
    <div v-if="!busy" class="install-actions">
      <a-button type="primary" :loading="licenseLoading" @click="openLicense">
        {{
          hasEmulator
            ? t('emulator2.avd.install.fetchComponents')
            : t('emulator2.avd.install.start')
        }}
      </a-button>
    </div>

    <a-modal
      v-model:open="licenseOpen"
      :title="t('emulator2.avd.install.licenseTitle')"
      width="720px"
      :ok-text="t('emulator2.avd.install.agreeAndStart')"
      :cancel-text="t('emulator.cancel')"
      :ok-button-props="{ disabled: !agreed }"
      :confirm-loading="starting"
      @ok="start"
    >
      <div class="license-intro">
        {{ t('emulator2.avd.install.licenseIntro', { source: licenseSource }) }}
      </div>
      <pre class="license-text">{{ licenseText }}</pre>
      <a-checkbox v-model:checked="agreed">{{ t('emulator2.avd.install.agree') }}</a-checkbox>
    </a-modal>
  </section>
</template>

<style scoped>
.block-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.install-hint,
.license-intro {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.install-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}

.progress-text {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.progress-message {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-detail {
  flex-shrink: 0;
  color: var(--ant-color-text-tertiary);
}

.install-actions {
  margin-top: 8px;
}

.license-text {
  max-height: 50vh;
  margin: 8px 0 12px;
  padding: 8px 12px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--ant-color-text);
}
</style>
