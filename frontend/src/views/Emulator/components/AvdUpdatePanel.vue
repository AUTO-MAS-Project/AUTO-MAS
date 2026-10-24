<script setup lang="ts">
/**
 * 魔改 AVD 根目录的「模拟器更新」：当前 / 最新版本，一个按钮，进度和结果。
 *
 * 按钮照 MFW 项目更新的做法：打开时不自动查，先显示「检查更新」；点了强制查一次（不走缓存、不带 CDK），
 * 查到新版本按钮变成「更新到 …」，再点才更新；已是最新、查失败时仍是「检查更新」。已经下好一版时直接
 * 显示「换上已下载好的 …」。点更新：有实例开着（或正在开机）就提示先关掉，什么都不动；没有时先确认
 * 「更新期间不会启动用到这个魔改 AVD 的脚本和实例」，再让后端开始（下载、核对、换上一次做完）。进度由
 * 后端经 WebSocket 推，操作结束后重新取一次状态。
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
import { canUpdate, samePath, updateButton, versionText } from '../avdLogic'

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
/** 这次打开后点过「检查更新」：之前不显示最新版本、不给「更新到 …」 */
const checked = ref(false)
const checking = ref(false)
const progress = ref<WSAvdUpdateProgressData | null>(null)
let subscription: string | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null
/** 卸载后在途请求回来，不再更新状态、也不再排下一次轮询 */
let disposed = false

const button = computed(() => (status.value ? updateButton(status.value, checked.value) : null))
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

const refresh = async () => {
  const root = props.root
  if (!root || disposed) return
  try {
    const next = await api.getStatus(root)
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

/** 「检查更新」：强制查一次（不走缓存、不带 CDK）；查不到时原因在 checkError 里，按钮仍是「检查更新」 */
const check = async () => {
  const root = props.root
  checking.value = true
  try {
    const next = await api.getStatus(root, true)
    if (disposed || root !== props.root) return
    status.value = next
    checked.value = true
  } catch (error) {
    message.error(describe(error))
  } finally {
    checking.value = false
  }
}

/** 确认后开始更新；后端发现有实例开着等原因没开始时把原因提示出来 */
const start = async () => {
  acting.value = true
  try {
    const response = await api.update(props.root)
    if (!response.ok) message.warning(response.message)
  } catch (error) {
    logger.error(`魔改 AVD 更新失败 (${props.root}): ${describe(error)}`)
    message.error(describe(error))
  } finally {
    acting.value = false
    await refresh()
  }
}

/** 点「更新」：先取一次最新状态，有实例开着（或正在开机）就提示先关掉；没有再确认 */
const run = async () => {
  const root = props.root
  acting.value = true
  let fresh: Emulator2AvdUpdateStatusOut
  try {
    fresh = await api.getStatus(root)
  } catch (error) {
    message.error(describe(error))
    return
  } finally {
    acting.value = false
  }
  if (disposed || root !== props.root) return
  status.value = fresh
  if (fresh.runningInstances) {
    message.warning(t('emulator2.avd.update.instancesRunning', { count: fresh.runningInstances }))
    return
  }
  if (!canUpdate(fresh)) return
  Modal.confirm({
    title: t('emulator2.avd.update.confirmTitle'),
    content: t('emulator2.avd.update.confirmContent'),
    okText: t('emulator2.avd.update.confirmOk'),
    cancelText: t('emulator.cancel'),
    onOk: start,
  })
}

watch(
  () => props.root,
  () => {
    progress.value = null
    checked.value = false
    void refresh()
  }
)

onMounted(() => {
  subscription = subscribe({ id: WS_ID_EMULATOR_MANAGER, type: WS_AVD_UPDATE_PROGRESS }, envelope =>
    onProgress(envelope.data)
  )
  void refresh()
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
            (checked && latest) || t('emulator2.avd.update.notChecked')
          }}
          <a-tag
            v-if="checked && !status.checkError && status.latestVersion && !status.updateAvailable"
            color="success"
            class="version-tag"
          >
            {{ t('emulator2.avd.update.upToDate') }}
          </a-tag>
        </span>
      </div>
      <div v-if="checked && status.checkError" class="update-error">
        {{ t('emulator2.avd.update.checkFailed', { reason: status.checkError }) }}
      </div>
      <a-alert
        v-if="checked && status.requiredAutoMas"
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
        <a-button v-if="button === 'check'" :loading="checking" @click="check">
          {{ t('emulator2.avd.update.check') }}
        </a-button>
        <a-button v-else-if="button" type="primary" :loading="acting" @click="run">
          {{
            button === 'install'
              ? t('emulator2.avd.update.install', { version: prepared })
              : status.assetSize
                ? t('emulator2.avd.update.update', {
                    version: latest,
                    size: formatBytes(status.assetSize),
                  })
                : t('emulator2.avd.update.updateNoSize', { version: latest })
          }}
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
