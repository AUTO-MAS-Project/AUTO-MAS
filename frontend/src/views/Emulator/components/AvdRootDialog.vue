<script setup lang="ts">
/**
 * 添加魔改 AVD：选根目录 → 看组件与电脑检查 → 组件缺着就同意许可协议后后台下载 → 添加。
 *
 * 组件齐了点「添加」走普通的路径纳管；下载时带上配置 ID，后端下载完成后自己把根目录加进配置，
 * 这里收到完成进度后刷新一次即可。已纳管的根目录也从这里看组件和电脑检查。
 * 电脑检查、组件列表、下载区各是一个子组件，状态与请求都在这里。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FolderOpenOutlined } from '@ant-design/icons-vue'

import type { Emulator2AvdSourceItem, Emulator2AvdStatusOut } from '@/api'
import { useAvdApi } from '@/composables/useAvdApi'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_EMULATOR2_AVD_INSTALL_PROGRESS,
  WS_ID_EMULATOR_MANAGER,
  type WSEmulator2AvdInstallProgressData,
} from '@/services/websocket/types'
import { canResume, isJobRunning, isRootAdded, samePath } from '../avdLogic'
import AvdComponentList from './AvdComponentList.vue'
import AvdDownloadPanel from './AvdDownloadPanel.vue'
import AvdPrecheckList from './AvdPrecheckList.vue'

const open = defineModel<boolean>('open', { required: true })
/** `addedRoots`：这条配置里已经纳管的魔改 AVD 根目录，已在里面的不再给「添加」 */
const props = defineProps<{ emulatorId: string; initialRoot?: string; addedRoots?: string[] }>()
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
const enablingHypervisor = ref(false)
/** 这次打开弹窗后已经开启成功：不重启不生效，按钮换成「重启后生效」 */
const hypervisorRestartPending = ref(false)

const current = computed(() =>
  status.value && samePath(checkedRoot.value, root.value) ? status.value : null
)
const ready = computed(() => Boolean(current.value?.ready))
const alreadyAdded = computed(() => isRootAdded(props.addedRoots ?? [], root.value))
const running = computed(() => isJobRunning(job.value))
const resumable = computed(() => canResume(current.value?.components, job.value))

const reset = () => {
  root.value = props.initialRoot ?? ''
  status.value = null
  checkedRoot.value = ''
  job.value = null
  agreed.value = false
}

/** `refresh`：用户主动检查（回车、点「检查」、选了目录）时跳过电脑检查的缓存 */
const check = async (refresh = false) => {
  const target = root.value.trim()
  if (!target) return
  checking.value = true
  try {
    const result = await api.getStatus(target, refresh)
    status.value = result
    checkedRoot.value = target
    job.value = result.job ?? null
    if (!result.ready && !licenseText.value) void loadLicense()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`读取魔改 AVD 状态失败 (${target}): ${detail}`)
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
  await check(true)
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
    logger.error(`开始下载魔改 AVD 组件失败: ${detail}`)
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
    logger.error(`取消下载魔改 AVD 组件失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.cancelFailed'))
  } finally {
    cancelling.value = false
  }
}

const addRoot = async () => {
  adding.value = true
  try {
    const response = await api.addRoot(props.emulatorId, root.value.trim())
    if (!response.ok) {
      const key = `emulator2.reason.${response.reason}`
      message.warning(response.reason && t(key) !== key ? t(key) : response.message)
      return
    }
    message.success(t('emulator2.toast.addOk', { count: 1 }))
    emit('added')
    open.value = false
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`添加魔改 AVD 失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.addFailed'))
  } finally {
    adding.value = false
  }
}

/** 只在用户点了「开启」后执行：后端提权跑 dism，会弹系统确认框；不重启电脑 */
const enableHypervisor = async () => {
  enablingHypervisor.value = true
  try {
    const result = await api.enableHypervisor()
    if (result.ok) {
      hypervisorRestartPending.value = true
      message.success(result.message, 8)
    } else if (result.reason === 'cancelled') {
      message.info(result.message)
    } else {
      message.warning(result.message || t('emulator2.avd.toast.hypervisorFailed'))
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`开启 Windows 虚拟机监控程序平台失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.hypervisorFailed'))
  } finally {
    enablingHypervisor.value = false
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
              @press-enter="check(true)"
            >
              <template #suffix>
                <FolderOpenOutlined class="root-pick" @click="pickRoot" />
              </template>
            </a-input>
            <a-button :loading="checking" :disabled="!root.trim()" @click="check(true)">
              {{ t('emulator2.avd.check') }}
            </a-button>
          </div>
        </a-form-item>
      </a-form>

      <template v-if="current">
        <AvdPrecheckList
          :items="current.prechecks ?? []"
          :enabling="enablingHypervisor"
          :restart-pending="hypervisorRestartPending"
          @enable-hypervisor="enableHypervisor"
        />
        <AvdComponentList :components="current.components ?? []" />
        <AvdDownloadPanel
          v-if="!ready"
          v-model:source-id="sourceId"
          v-model:include-launcher="includeLauncher"
          v-model:agreed="agreed"
          :required-disk-bytes="current.requiredDiskBytes"
          :free-disk-bytes="current.freeDiskBytes"
          :license-text="licenseText"
          :license-loading="licenseLoading"
          :job="job"
          :running="running"
          :sources="sources"
          :probing="probing"
          @probe="probe"
        />
      </template>

      <div class="dialog-footer">
        <a-button @click="open = false">
          {{ alreadyAdded ? t('emulator2.avd.close') : t('emulator.cancel') }}
        </a-button>
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
        <a-button
          v-else-if="!alreadyAdded"
          type="primary"
          :loading="adding"
          :disabled="!ready"
          @click="addRoot"
        >
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

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>
