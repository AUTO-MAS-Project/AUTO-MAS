<script setup lang="ts">
/**
 * 魔改 AVD 根目录的「模拟器更新」：当前 / 最新版本、更新公告、下载、安装、回退、空闲时自动安装。
 *
 * 默认只提示、由用户手动装。下载时实例开着也行；安装要先关掉实例（只走正常关机），有实例开着时
 * 先问一句再关。进度由后端经 WebSocket 推，操作结束（成功 / 失败 / 取消）后重新取一次状态。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal, message } from 'ant-design-vue'

import type { Emulator2AvdUpdateActionOut, Emulator2AvdUpdateStatusOut } from '@/api'
import { useAvdUpdateApi } from '@/composables/useAvdUpdateApi'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_AVD_UPDATE_PROGRESS,
  WS_ID_EMULATOR_MANAGER,
  type WSAvdUpdateProgressData,
} from '@/services/websocket/types'
import { formatBytes, formatSpeed } from '@/utils/byteFormat'
import { samePath, updateActions, versionLabel } from '../avdLogic'
import AvdReleaseNotes from './AvdReleaseNotes.vue'

const props = defineProps<{ root: string }>()
/** 换上或回退成功：组件与电脑检查要跟着刷新 */
const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const api = useAvdUpdateApi()

/** 没收到 WebSocket 时的兜底轮询间隔（毫秒），只在有操作在跑时轮询 */
const BUSY_POLL_MS = 2000

const status = ref<Emulator2AvdUpdateStatusOut | null>(null)
const checking = ref(false)
const acting = ref(false)
const progress = ref<WSAvdUpdateProgressData | null>(null)
let subscription: string | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null

const actions = computed(() =>
  status.value
    ? updateActions(status.value)
    : { download: false, cancel: false, install: false, rollback: false }
)
const current = computed(() =>
  versionLabel(status.value?.currentBuild, status.value?.currentVersion)
)
const latest = computed(() => versionLabel(status.value?.latestBuild, status.value?.latestVersion))
const running = computed(() => {
  const item = progress.value ?? status.value?.progress
  return item?.status === 'running' ? item : null
})
const failedMessage = computed(() => {
  const item = progress.value ?? status.value?.progress
  return item?.status === 'failed' ? item.message : ''
})
const progressDetail = computed(() => {
  const item = running.value
  if (!item?.totalBytes) return ''
  const parts = [`${formatBytes(item.downloadedBytes ?? 0)} / ${formatBytes(item.totalBytes)}`]
  if (item.stage === 'downloading' && item.speedBytesPerSec)
    parts.push(formatSpeed(item.speedBytesPerSec))
  return parts.join(' · ')
})
const checkedAt = computed(() =>
  status.value?.checkedAt ? new Date(status.value.checkedAt).toLocaleString() : ''
)

const describe = (error: unknown) => (error instanceof Error ? error.message : String(error))

const schedulePoll = () => {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = status.value?.busy ? setTimeout(() => void refresh(), BUSY_POLL_MS) : null
}

/** ``check``：打开时查一次（走后端 4 小时缓存）；``force``：用户点「检查更新」 */
const refresh = async ({ check = false, force = false } = {}) => {
  if (!props.root) return
  if (check) checking.value = true
  try {
    status.value = check ? await api.check(props.root, force) : await api.getStatus(props.root)
    if (!status.value.busy) progress.value = null
  } catch (error) {
    logger.warn(`读取魔改 AVD 更新状态失败 (${props.root}): ${describe(error)}`)
    if (check) message.error(describe(error))
  } finally {
    checking.value = false
    schedulePoll()
  }
}

const onProgress = (data: WSAvdUpdateProgressData) => {
  if (!samePath(data.root, props.root)) return
  progress.value = data
  if (data.status !== 'running') {
    if (data.status === 'success' && ['installed', 'rolled_back'].includes(data.stage))
      emit('changed')
    void refresh()
  }
}

/** 动作「没开始」时后端给原因（如已是最新、要先关实例），照原话提示 */
const run = async (request: () => Promise<Emulator2AvdUpdateActionOut>) => {
  acting.value = true
  try {
    const response = await request()
    if (!response.ok) message.warning(response.message)
    return response
  } catch (error) {
    logger.error(`魔改 AVD 更新操作失败 (${props.root}): ${describe(error)}`)
    message.error(describe(error))
    return null
  } finally {
    acting.value = false
    await refresh()
  }
}

const download = () => run(() => api.download(props.root))
const cancel = () => run(() => api.cancel(props.root))

/** 安装 / 回退：有实例开着就先问一句，同意后让后端先正常关掉它们 */
const swap = async (kind: 'install' | 'rollback') => {
  const count = status.value?.runningInstances ?? 0
  const version = kind === 'install' ? status.value?.preparedVersion : status.value?.previousVersion
  const request = (close: boolean) =>
    kind === 'install' ? api.install(props.root, close) : api.rollback(props.root, close)
  if (kind === 'install' && !count) return void run(() => request(false))
  Modal.confirm({
    title: t(
      kind === 'install'
        ? 'emulator2.avd.update.confirmInstallTitle'
        : 'emulator2.avd.update.confirmRollbackTitle',
      { version }
    ),
    content: count
      ? t('emulator2.avd.update.confirmClose', { count })
      : t('emulator2.avd.update.confirmRollback'),
    okText: t('emulator2.avd.update.confirmOk'),
    cancelText: t('emulator.cancel'),
    onOk: () => run(() => request(count > 0)),
  })
}

const setAutoInstall = async (value: boolean) => {
  try {
    status.value = await api.setAutoInstall(props.root, value)
  } catch (error) {
    message.error(describe(error))
  }
}

watch(
  () => props.root,
  () => {
    progress.value = null
    void refresh({ check: true })
  }
)

onMounted(() => {
  subscription = subscribe({ id: WS_ID_EMULATOR_MANAGER, type: WS_AVD_UPDATE_PROGRESS }, envelope =>
    onProgress(envelope.data)
  )
  void refresh({ check: true })
})

onBeforeUnmount(() => {
  if (subscription) unsubscribe(subscription)
  if (pollTimer) clearTimeout(pollTimer)
})

defineExpose({ refresh })
</script>

<template>
  <section class="avd-update">
    <h4 class="block-title">{{ t('emulator2.avd.update.title') }}</h4>
    <div v-if="!status" class="update-loading">
      <a-spin :spinning="checking || api.loading.value" />
    </div>
    <a-alert
      v-else-if="!status.updatable"
      type="info"
      show-icon
      :message="status.notUpdatableReason"
    />
    <div v-else class="update-body">
      <a-alert
        v-if="status.belowMinimum"
        type="error"
        show-icon
        :message="t('emulator2.avd.update.belowMinimum', { current, minimum: status.minimumBuild })"
      />
      <div class="version-row">
        <span>{{ t('emulator2.avd.update.current') }}：{{ current || '—' }}</span>
        <span>
          {{ t('emulator2.avd.update.latest') }}：
          <template v-if="status.latestVersion">{{ latest }}</template>
          <template v-else>{{ t('emulator2.avd.update.notChecked') }}</template>
          <a-tag
            v-if="status.latestVersion && !status.updateAvailable"
            color="success"
            class="version-tag"
          >
            {{ t('emulator2.avd.update.upToDate') }}
          </a-tag>
        </span>
        <a-button
          size="small"
          :loading="checking"
          :disabled="status.busy"
          @click="refresh({ check: true, force: true })"
        >
          {{ t('emulator2.avd.update.check') }}
        </a-button>
      </div>
      <div class="update-meta">
        <span v-if="checkedAt">{{ t('emulator2.avd.update.checkedAt', { time: checkedAt }) }}</span>
        <span v-if="status.checkError" class="update-error">
          {{ t('emulator2.avd.update.checkFailed', { reason: status.checkError }) }}
        </span>
      </div>
      <a-alert
        v-if="status.requiredAutoMas"
        type="warning"
        show-icon
        :message="t('emulator2.avd.update.requiredAutoMas', { version: status.requiredAutoMas })"
      />
      <AvdReleaseNotes
        v-if="status.updateAvailable"
        :changes="status.changes ?? []"
        :announcement="status.announcement ?? ''"
        :latest="latest"
        :release-url="status.releaseUrl ?? ''"
      />
      <div v-if="running" class="update-progress">
        <div class="progress-text">
          <span>{{ running.message }}</span>
          <span class="progress-detail">{{ progressDetail }}</span>
        </div>
        <a-progress
          :percent="Math.round(running.percent ?? 0)"
          :status="running.percent == null ? 'active' : 'normal'"
          size="small"
        />
      </div>
      <a-alert v-else-if="failedMessage" type="error" show-icon :message="failedMessage" />
      <a-alert
        v-if="status.preparedVersion && !running"
        type="success"
        show-icon
        :message="t('emulator2.avd.update.prepared', { version: status.preparedVersion })"
      />
      <a-alert
        v-if="status.awaitingBoot && status.previousVersion"
        type="info"
        show-icon
        :message="t('emulator2.avd.update.awaitingBoot', { version: status.previousVersion })"
      />
      <a-alert
        v-if="status.busyProcesses?.length"
        type="warning"
        show-icon
        :message="
          t('emulator2.avd.update.busyProcesses', { names: status.busyProcesses.join('、') })
        "
      />
      <div class="update-actions">
        <a-button v-if="actions.download" type="primary" :loading="acting" @click="download">
          {{
            t('emulator2.avd.update.download', {
              version: latest,
              size: formatBytes(status.assetSize ?? 0),
            })
          }}
        </a-button>
        <a-button v-if="actions.cancel" :loading="acting" @click="cancel">
          {{ t('emulator2.avd.update.cancel') }}
        </a-button>
        <a-button v-if="actions.install" type="primary" :loading="acting" @click="swap('install')">
          {{
            status.runningInstances
              ? t('emulator2.avd.update.installClose', {
                  version: status.preparedVersion,
                  count: status.runningInstances,
                })
              : t('emulator2.avd.update.install', { version: status.preparedVersion })
          }}
        </a-button>
        <a-button v-if="actions.rollback" danger :loading="acting" @click="swap('rollback')">
          {{ t('emulator2.avd.update.rollback', { version: status.previousVersion }) }}
        </a-button>
      </div>
      <div class="auto-install">
        <a-checkbox
          :checked="Boolean(status.autoInstall)"
          @change="
            (event: { target: { checked: boolean } }) => setAutoInstall(event.target.checked)
          "
        >
          {{ t('emulator2.avd.update.autoInstall') }}
        </a-checkbox>
        <div class="auto-install-hint">{{ t('emulator2.avd.update.autoInstallHint') }}</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.block-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.update-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 64px;
}

.update-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.version-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
}

.version-tag {
  margin-left: 6px;
}

.update-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.update-error {
  color: var(--ant-color-error);
}

.progress-text {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.progress-detail {
  color: var(--ant-color-text-tertiary);
}

.update-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.auto-install-hint {
  margin-left: 24px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
