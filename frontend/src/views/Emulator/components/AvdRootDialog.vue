<script setup lang="ts">
/**
 * 添加官方模拟器（AVD）：选根目录 → 看组件与电脑检查 → 组件缺着就同意许可协议后后台下载 → 添加。
 *
 * 组件齐了点「添加」走普通的路径纳管；下载时带上配置 ID，后端下载完成后自己把根目录加进配置，
 * 这里收到完成进度后刷新一次即可。已纳管的根目录也从这里看组件和电脑检查。
 */
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FolderOpenOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'

import { Emulator20Service } from '@/api'
import type {
  Emulator2AvdComponentItem,
  Emulator2AvdPrecheckItem,
  Emulator2AvdSourceItem,
  Emulator2AvdStatusOut,
} from '@/api'
import { useAvdApi } from '@/composables/useAvdApi'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_EMULATOR2_AVD_INSTALL_PROGRESS,
  WS_ID_EMULATOR_MANAGER,
  type WSEmulator2AvdInstallProgressData,
} from '@/services/websocket/types'
import { formatBytes, formatSpeed } from '@/utils/byteFormat'
import {
  canResume,
  componentState,
  isJobRunning,
  jobPercent,
  precheckLevel,
  samePath,
  type PrecheckLevel,
} from '../avdLogic'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ emulatorId: string; initialRoot?: string }>()
const emit = defineEmits<{ added: [] }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const api = useAvdApi()

const root = ref('')
const checking = ref(false)
const status = ref<Emulator2AvdStatusOut | null>(null)
/** 状态是哪个根目录查出来的；输入框改了之后旧结果不再算数 */
const checkedRoot = ref('')
const job = ref<WSEmulator2AvdInstallProgressData | null>(null)

const sources = ref<Emulator2AvdSourceItem[]>([])
const sourceId = ref<string | null>(null)
const probing = ref(false)
const licenseText = ref('')
const licenseLoading = ref(false)
const agreed = ref(false)
const includeLauncher = ref(true)
const starting = ref(false)
const cancelling = ref(false)
const adding = ref(false)

const current = computed(() =>
  status.value && samePath(checkedRoot.value, root.value) ? status.value : null
)
const ready = computed(() => Boolean(current.value?.ready))
const running = computed(() => isJobRunning(job.value))
const resumable = computed(() => canResume(current.value?.components, job.value))
const percent = computed(() => jobPercent(job.value))

const reset = () => {
  root.value = props.initialRoot ?? ''
  status.value = null
  checkedRoot.value = ''
  job.value = null
  agreed.value = false
}

const check = async () => {
  const target = root.value.trim()
  if (!target) return
  checking.value = true
  try {
    const result = await api.getStatus(target)
    status.value = result
    checkedRoot.value = target
    job.value = result.job ?? null
    if (!result.ready && !licenseText.value) void loadLicense()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`读取官方模拟器状态失败 (${target}): ${detail}`)
    message.error(detail || t('emulator2.avd.toast.statusFailed'))
  } finally {
    checking.value = false
  }
}

const pickRoot = async () => {
  if (!window.electronAPI?.selectFolder) return
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  root.value = picked
  await check()
}

const loadLicense = async () => {
  licenseLoading.value = true
  try {
    licenseText.value = (await api.getLicense(sourceId.value)).text ?? ''
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`获取许可协议失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.licenseFailed'))
  } finally {
    licenseLoading.value = false
  }
}

const probe = async () => {
  probing.value = true
  try {
    const result = await api.probeSources()
    sources.value = result.sources ?? []
    if (result.recommended) sourceId.value = result.recommended
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`下载源测速失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.probeFailed'))
  } finally {
    probing.value = false
  }
}

const sourceOptions = computed(() => [
  { value: null, label: t('emulator2.avd.sourceAuto') },
  ...sources.value.map(item => ({
    value: item.id,
    label: item.ok
      ? `${item.name} · ${formatSpeed(item.speedBytesPerSec ?? 0)}`
      : `${item.name} · ${t('emulator2.avd.sourceDown')}`,
    disabled: !item.ok,
  })),
])

const startDownload = async () => {
  starting.value = true
  try {
    const result = await api.startInstall({
      root: root.value.trim(),
      acceptLicense: agreed.value,
      source: sourceId.value,
      includeLauncher: includeLauncher.value,
      emulatorId: props.emulatorId,
    })
    if (!result.ok) {
      message.warning(result.message || t('emulator2.avd.toast.startFailed'))
      return
    }
    if (result.reason === 'ready') {
      // 组件本来就齐，后端已经把根目录加进配置
      emit('added')
      await check()
      return
    }
    job.value = result.job ?? job.value
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`开始下载官方模拟器组件失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.startFailed'))
  } finally {
    starting.value = false
  }
}

const cancelDownload = async () => {
  cancelling.value = true
  try {
    const result = await api.cancelInstall(root.value.trim())
    if (!result.ok) message.warning(result.message || t('emulator2.avd.toast.cancelFailed'))
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`取消下载官方模拟器组件失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.cancelFailed'))
  } finally {
    cancelling.value = false
  }
}

const addRoot = async () => {
  adding.value = true
  try {
    const response = await Emulator20Service.addPathApiEmulator2PathsAddPost({
      emulatorId: props.emulatorId,
      installPath: root.value.trim(),
      alias: null,
    })
    if (response.code !== 200 || !response.ok) {
      const key = `emulator2.reason.${response.reason}`
      message.warning(response.reason && t(key) !== key ? t(key) : response.message)
      return
    }
    message.success(t('emulator2.toast.addOk', { count: 1 }))
    emit('added')
    open.value = false
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`添加官方模拟器失败: ${detail}`)
    message.error(t('emulator2.avd.toast.addFailed'))
  } finally {
    adding.value = false
  }
}

const onProgress = (data: WSEmulator2AvdInstallProgressData) => {
  if (!samePath(data.root, root.value)) return
  job.value = data
  if (data.status === 'running') return
  if (data.status === 'success') {
    message.success(t('emulator2.avd.toast.downloadDone'))
    emit('added')
  } else if (data.status === 'failed') {
    message.error(t('emulator2.avd.toast.downloadFailed', { reason: data.error || data.message }))
  }
  void check()
}

const stageText = (stage: string) => {
  const key = `emulator2.avd.stage.${stage}`
  const text = t(key)
  return text === key ? stage : text
}

const componentText = (item: Emulator2AvdComponentItem) => {
  const state = componentState(item)
  if (state === 'ready') return t('emulator2.avd.componentReady')
  if (state === 'partial') {
    return t('emulator2.avd.componentPartial', {
      size: `${formatBytes(item.downloadedBytes ?? 0)} / ${formatBytes(item.sizeBytes ?? 0)}`,
    })
  }
  return t('emulator2.avd.componentMissing')
}

const componentColor = (item: Emulator2AvdComponentItem) => {
  const state = componentState(item)
  if (state === 'ready') return 'success'
  if (state === 'partial') return 'processing'
  return item.optional ? 'default' : 'warning'
}

const LEVEL_COLOR: Record<PrecheckLevel, string> = {
  ok: 'success',
  error: 'error',
  warning: 'warning',
  unknown: 'default',
}

const levelText = (level: PrecheckLevel) => t(`emulator2.avd.precheck.${level}`)

const failing = (item: Emulator2AvdPrecheckItem) => {
  const level = precheckLevel(item)
  return level === 'error' || level === 'warning'
}

watch(open, value => {
  if (!value) return
  reset()
  if (root.value) void check()
})

let progressSubscription: string | null = null

onMounted(() => {
  progressSubscription = subscribe(
    { id: WS_ID_EMULATOR_MANAGER, type: WS_EMULATOR2_AVD_INSTALL_PROGRESS },
    envelope => onProgress(envelope.data)
  )
})

onUnmounted(() => {
  if (progressSubscription) unsubscribe(progressSubscription)
})
</script>

<template>
  <a-modal v-model:open="open" :title="t('emulator2.avd.title')" width="760px" :footer="null">
    <div class="avd-root-dialog">
      <a-form layout="vertical">
        <a-form-item :label="t('emulator2.avd.root')">
          <div class="root-row">
            <a-input
              v-model:value="root"
              :placeholder="t('emulator2.avd.rootPlaceholder')"
              @press-enter="check"
            >
              <template #suffix>
                <FolderOpenOutlined class="root-pick" @click="pickRoot" />
              </template>
            </a-input>
            <a-button :loading="checking" :disabled="!root.trim()" @click="check">
              {{ t('emulator2.avd.check') }}
            </a-button>
          </div>
        </a-form-item>
      </a-form>

      <template v-if="current">
        <h4 class="block-title">{{ t('emulator2.avd.prechecks') }}</h4>
        <div class="precheck-list">
          <template v-for="item in current.prechecks ?? []" :key="item.id">
            <a-alert
              v-if="failing(item)"
              :type="precheckLevel(item) === 'error' ? 'error' : 'warning'"
              show-icon
              :message="`${item.title}：${item.reason}`"
              :description="item.advice || undefined"
            />
            <div v-else class="precheck-row">
              <a-tag :color="LEVEL_COLOR[precheckLevel(item)]">
                {{ levelText(precheckLevel(item)) }}
              </a-tag>
              <span class="precheck-title">{{ item.title }}</span>
              <span class="precheck-reason">{{ item.reason }}</span>
            </div>
          </template>
        </div>

        <h4 class="block-title">{{ t('emulator2.avd.components') }}</h4>
        <div class="component-list">
          <div v-for="item in current.components ?? []" :key="item.id" class="component-row">
            <span class="component-name">{{ item.name }}</span>
            <span class="component-meta">
              {{ item.version }}
              <template v-if="item.sizeBytes"> · {{ formatBytes(item.sizeBytes) }}</template>
              <template v-if="item.optional"> · {{ t('emulator2.avd.optional') }}</template>
            </span>
            <a-tag :color="componentColor(item)">{{ componentText(item) }}</a-tag>
          </div>
        </div>

        <div v-if="!ready" class="download-block">
          <p v-if="current.requiredDiskBytes" class="disk-line">
            {{
              t('emulator2.avd.diskNeed', {
                need: formatBytes(current.requiredDiskBytes),
                free:
                  current.freeDiskBytes === null || current.freeDiskBytes === undefined
                    ? '—'
                    : formatBytes(current.freeDiskBytes),
              })
            }}
          </p>

          <template v-if="!running">
            <a-form layout="vertical">
              <a-form-item :label="t('emulator2.avd.source')">
                <div class="root-row">
                  <a-select v-model:value="sourceId" :options="sourceOptions" style="flex: 1" />
                  <a-button :icon="h(ThunderboltOutlined)" :loading="probing" @click="probe">
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
                job.status === 'failed'
                  ? 'exception'
                  : job.status === 'success'
                    ? 'success'
                    : 'active'
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

      <div class="dialog-footer">
        <a-button @click="open = false">{{ t('emulator.cancel') }}</a-button>
        <template v-if="current && !ready">
          <a-button v-if="running" danger :loading="cancelling" @click="cancelDownload">
            {{ t('emulator2.avd.cancelDownload') }}
          </a-button>
          <a-button
            v-else
            type="primary"
            :loading="starting"
            :disabled="!agreed"
            @click="startDownload"
          >
            {{ resumable ? t('emulator2.avd.resume') : t('emulator2.avd.download') }}
          </a-button>
        </template>
        <a-button v-else type="primary" :loading="adding" :disabled="!ready" @click="addRoot">
          {{ t('emulator2.add') }}
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.root-row {
  display: flex;
  gap: 8px;
}

.root-pick {
  cursor: pointer;
  color: var(--ant-color-text-secondary);
}

.block-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.precheck-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.precheck-row,
.component-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.precheck-title,
.component-name {
  flex-shrink: 0;
  font-weight: 500;
}

.precheck-reason,
.component-meta {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.component-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.download-block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.disk-line {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
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

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>
