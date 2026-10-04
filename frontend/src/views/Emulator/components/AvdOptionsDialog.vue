<script setup lang="ts">
/**
 * 已有魔改 AVD 实例的选项：打开时读一次，保存只提交改过的项，下次启动生效。
 * 另有「安装 APK」：选一个本机 .apk 装进开着的实例，装完才返回。
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'

import { useAvdApi } from '@/composables/useAvdApi'
import { defaultAvdOptions, optionsChanges, optionsFromOut, type AvdOptionsForm } from '../avdLogic'
import AvdOptionsFields from './AvdOptionsFields.vue'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ emulatorId: string; deviceSlot: string; title: string }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const { getInstanceOptions, setInstanceOptions, installApk } = useAvdApi()

const loading = ref(false)
const saving = ref(false)
const form = ref<AvdOptionsForm>(defaultAvdOptions())
const baseline = ref<AvdOptionsForm>(defaultAvdOptions())
/** 软件渲染：首次开机检测到没有可用显卡驱动时由后端记下 */
const softwareRenderer = ref(false)

const load = async () => {
  loading.value = true
  try {
    const out = await getInstanceOptions(props.emulatorId, props.deviceSlot)
    form.value = optionsFromOut(out)
    baseline.value = { ...form.value }
    softwareRenderer.value = Boolean(out.softwareRenderer)
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`读取官方模拟器实例 #${props.deviceSlot} 的选项失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.optionsLoadFailed'))
    open.value = false
  } finally {
    loading.value = false
  }
}

// 父组件第一次挂上这个弹窗时 open 已经是 true，所以要 immediate
watch(
  () => [open.value, props.deviceSlot] as const,
  ([value]) => {
    if (value) void load()
  },
  { immediate: true }
)

const installing = ref(false)

const pickAndInstallApk = async () => {
  if (!window.electronAPI?.selectFile) return
  const picked = await window.electronAPI.selectFile([
    { name: t('emulator2.avd.apkFiles'), extensions: ['apk'] },
  ])
  const apkPath = picked?.[0]
  if (!apkPath) return
  installing.value = true
  try {
    await installApk(props.emulatorId, props.deviceSlot, apkPath)
    const name = apkPath.split(/[\\/]/).pop() ?? apkPath
    message.success(t('emulator2.avd.toast.apkOk', { name }))
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`魔改 AVD 实例 #${props.deviceSlot} 安装 APK 失败 (${apkPath}): ${detail}`)
    message.error(detail || t('emulator2.avd.toast.apkFailed'))
  } finally {
    installing.value = false
  }
}

const save = async () => {
  const changes = optionsChanges(baseline.value, form.value)
  if (!Object.keys(changes).length) {
    open.value = false
    return
  }
  saving.value = true
  try {
    await setInstanceOptions(props.emulatorId, props.deviceSlot, changes)
    message.success(t('emulator2.avd.toast.optionsOk'))
    open.value = false
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`保存官方模拟器实例 #${props.deviceSlot} 的选项失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.optionsFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-modal
    v-model:open="open"
    :title="t('emulator2.avd.optionsTitle')"
    width="560px"
    :confirm-loading="saving"
    :ok-text="t('emulator2.save')"
    :ok-button-props="{ disabled: loading }"
    @ok="save"
  >
    <p>
      <strong>#{{ deviceSlot }}</strong>
      — {{ title }}
    </p>
    <div v-if="loading" class="options-loading"><a-spin /></div>
    <a-form v-else layout="vertical">
      <AvdOptionsFields v-model="form" />
    </a-form>
    <a-alert
      v-if="softwareRenderer"
      type="warning"
      show-icon
      :message="t('emulator2.avd.softwareRenderer')"
      style="margin-bottom: 12px"
    />
    <a-alert type="info" show-icon :message="t('emulator2.avd.optionsHint')" />
    <div class="apk-row">
      <a-button :loading="installing" :disabled="loading" @click="pickAndInstallApk">
        {{ t('emulator2.avd.installApk') }}
      </a-button>
      <span class="apk-hint">{{ t('emulator2.avd.installApkHint') }}</span>
    </div>
  </a-modal>
</template>

<style scoped>
.apk-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.apk-hint {
  min-width: 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.options-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
}
</style>
