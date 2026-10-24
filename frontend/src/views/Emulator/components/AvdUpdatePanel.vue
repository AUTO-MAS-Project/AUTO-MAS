<script setup lang="ts">
/**
 * 魔改 AVD 根目录的「模拟器更新」：当前 / 最新版本，一个「更新」按钮（下载、核对、换上一次做完），
 * 进度、结果和取消。
 *
 * 有实例开着时后端先返回要关几台，问一句、同意后再让后端只走正常关机关掉它们。进度由后端经 WebSocket
 * 推，操作结束后重新取一次状态。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal, message } from 'ant-design-vue'

import type { Emulator2AvdUpdateStatusOut } from '@/api'
import { useAvdUpdateApi } from '@/composables/useAvdUpdateApi'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_AVD_UPDATE_PROGRESS,
  WS_ID_EMULATOR_MANAGER,
  type WSAvdUpdateProgressData,
} from '@/services/websocket/types'
import { formatBytes, formatSpeed } from '@/utils/byteFormat'
import { samePath, updateActions, versionText } from '../avdLogic'

const props = defineProps<{ root: string }>()
/** 换上成功：组件与电脑检查要跟着刷新 */
const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const api = useAvdUpdateApi()

/** 没收到 WebSocket 时的兜底轮询间隔（毫秒），只在有更新在跑时轮询 */
const BUSY_POLL_MS = 2000

const status = ref<Emulator2AvdUpdateStatusOut | null>(null)
const acting = ref(false)
const progress = ref<WSAvdUpdateProgressData | null>(null)
let subscription: string | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null
/** 卸载后在途请求回来，不再更新状态、也不再排下一次轮询 */
let disposed = false

const actions = computed(() =>
  status.value ? updateActions(status.value) : { update: false, cancel: false }
)
const current = computed(() => versionText(status.value?.currentVersion))
const latest = computed(() => versionText(status.value?.latestVersion))
const minimum = computed(() => versionText(status.value?.minimumVersion))
const prepared = computed(() => versionText(status.value?.preparedVersion))
/** 正在跑的进度，或最近一次的结果（成功 / 失败 / 已下载好但没换上） */
const shown = computed(() => progress.value ?? status.value?.progress ?? null)
const running = computed(() => (shown.value?.status === 'running' ? shown.value : null))
const resultType = computed(() => {
  const item = shown.value
  if (!item || item.status === 'running' || !item.message) return null
  if (item.status === 'success') return 'success'
  if (item.status !== 'failed') return 'info'
  return item.stage === 'staged' ? 'warning' : 'error'
})
const progressDetail = computed(() => {
  const item = running.value
  if (!item?.totalBytes) return ''
  const parts = [`${formatBytes(item.downloadedBytes ?? 0)} / ${formatBytes(item.totalBytes)}`]
  if (item.stage === 'downloading' && item.speedBytesPerSec)
    parts.push(formatSpeed(item.speedBytesPerSec))
  return parts.join(' · ')
})

const describe = (error: unknown) => (error instanceof Error ? error.message : String(error))

const schedulePoll = () => {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer =
    !disposed && status.value?.busy ? setTimeout(() => void refresh(), BUSY_POLL_MS) : null
}

/** ``check``：打开时顺带查一次更新（走后端 4 小时缓存） */
const refresh = async (check = false) => {
  const root = props.root
  if (!root || disposed) return
  try {
    const next = await api.getStatus(root, check)
    // 等的时候组件卸载了、或者换了根目录：这份结果已经不是当前的
    if (disposed || root !== props.root) return
    status.value = next
    if (!next.busy) progress.value = null
  } catch (error) {
    logger.warn(`读取魔改 AVD 更新状态失败 (${props.root}): ${describe(error)}`)
  } finally {
    schedulePoll()
  }
}

const onProgress = (data: WSAvdUpdateProgressData) => {
  if (!samePath(data.root, props.root)) return
  progress.value = data
  if (data.status !== 'running') {
    if (data.status === 'success' && data.stage === 'installed') emit('changed')
    void refresh()
  }
}

/** 更新；有实例开着时后端不动手、返回要关几台，问过用户再带 ``closeInstances`` 重来 */
const run = async (closeInstances: boolean) => {
  acting.value = true
  try {
    const response = await api.update(props.root, closeInstances)
    if (response.reason === 'instances_running') {
      Modal.confirm({
        title: t('emulator2.avd.update.confirmCloseTitle'),
        content: t('emulator2.avd.update.confirmClose', { count: response.runningInstances }),
        okText: t('emulator2.avd.update.confirmOk'),
        cancelText: t('emulator.cancel'),
        onOk: () => run(true),
      })
    } else if (!response.ok) {
      message.warning(response.message)
    }
  } catch (error) {
    logger.error(`魔改 AVD 更新失败 (${props.root}): ${describe(error)}`)
    message.error(describe(error))
  } finally {
    acting.value = false
    await refresh()
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
    void refresh(true)
  }
)

onMounted(() => {
  subscription = subscribe({ id: WS_ID_EMULATOR_MANAGER, type: WS_AVD_UPDATE_PROGRESS }, envelope =>
    onProgress(envelope.data)
  )
  void refresh(true)
})

onBeforeUnmount(() => {
  disposed = true
  if (subscription) unsubscribe(subscription)
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <section class="avd-update">
    <h4 class="block-title">{{ t('emulator2.avd.update.title') }}</h4>
    <div v-if="!status" class="update-loading">
      <a-spin :spinning="api.loading.value" />
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
        :message="t('emulator2.avd.update.belowMinimum', { current, minimum })"
      />
      <div class="version-row">
        <span>{{ t('emulator2.avd.update.current') }}：{{ current || '—' }}</span>
        <span>
          {{ t('emulator2.avd.update.latest') }}：{{
            latest || t('emulator2.avd.update.notChecked')
          }}
          <a-tag
            v-if="status.latestVersion && !status.updateAvailable"
            color="success"
            class="version-tag"
          >
            {{ t('emulator2.avd.update.upToDate') }}
          </a-tag>
        </span>
      </div>
      <div v-if="status.checkError" class="update-error">
        {{ t('emulator2.avd.update.checkFailed', { reason: status.checkError }) }}
      </div>
      <a-alert
        v-if="status.requiredAutoMas"
        type="warning"
        show-icon
        :message="t('emulator2.avd.update.requiredAutoMas', { version: status.requiredAutoMas })"
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
      <a-alert v-else-if="resultType" :type="resultType" show-icon :message="shown?.message" />
      <div class="update-actions">
        <a-button v-if="actions.update" type="primary" :loading="acting" @click="run(false)">
          {{
            prepared
              ? t('emulator2.avd.update.install', { version: prepared })
              : status.assetSize
                ? t('emulator2.avd.update.update', {
                    version: latest,
                    size: formatBytes(status.assetSize),
                  })
                : t('emulator2.avd.update.updateNoSize', { version: latest })
          }}
        </a-button>
        <a-button v-if="actions.cancel" @click="cancel">
          {{ t('emulator2.avd.update.cancel') }}
        </a-button>
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

.update-error {
  font-size: 12px;
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
</style>
