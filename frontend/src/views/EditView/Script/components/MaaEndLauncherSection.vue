<template>
  <a-row :gutter="24">
    <a-col :xs="24" :md="12">
      <a-form-item :help="launchHint">
        <template #label>
          <span class="form-label">
            {{ t('edit.launchType') }}
            <a-tooltip :title="t('edit.maaEndLaunchTypeHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-select
          :value="launchMode"
          :options="launchModeOptions"
          size="large"
          :disabled="disabled"
          :loading="capabilitiesLoading"
          @change="emit('changeLaunchMode', $event)"
        />
      </a-form-item>
    </a-col>
    <a-col :xs="24" :md="12">
      <a-form-item
        :validate-status="canConfigureLauncher && error ? 'error' : undefined"
        :help="
          canConfigureLauncher && error ? error : !usesMasLauncher ? nativeLauncherHelp : undefined
        "
      >
        <template #label>
          <span class="form-label">{{ t('edit.maaEndLauncherPath') }}</span>
        </template>
        <a-space-compact v-if="usesMasLauncher || source === 'manual'" block size="large">
          <a-input
            :value="path"
            :title="path"
            :placeholder="
              t(
                usesMasLauncher
                  ? 'edit.maaEndPickClientBeforeLauncher'
                  : 'edit.maaEndLauncherSourceNative'
              )
            "
            :aria-label="t('edit.maaEndLauncherPath')"
            size="large"
            readonly
            :disabled="disabled || !canConfigureLauncher"
            class="launcher-path-input"
          />
          <a-button
            :loading="detecting || saving"
            :disabled="
              disabled ||
              !canConfigureLauncher ||
              (usesMasLauncher && source === 'auto' && !canDetect)
            "
            size="large"
            @click="usesMasLauncher && source === 'auto' ? emit('refresh') : emit('selectFile')"
          >
            <template #icon>
              <ReloadOutlined v-if="usesMasLauncher && source === 'auto'" />
              <FolderOpenOutlined v-else />
            </template>
            {{
              t(
                usesMasLauncher && source === 'auto'
                  ? 'edit.maaEndRefreshLauncher'
                  : 'edit.maaEndChangeLauncher'
              )
            }}
          </a-button>
        </a-space-compact>
        <div class="launcher-source">
          <a-radio-group
            :value="source"
            :options="sourceOptions"
            :aria-label="t('edit.maaEndLauncherPathSource')"
            :disabled="disabled || detecting || !canConfigureLauncher"
            @change="emit('changeSource', $event.target.value)"
          />
          <a-tooltip
            :title="
              !usesMasLauncher
                ? nativeLauncherHint
                : t(
                    source === 'auto'
                      ? 'edit.maaEndLauncherAutoHint'
                      : 'edit.maaEndLauncherManualHint'
                  )
            "
          >
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
      </a-form-item>
    </a-col>
  </a-row>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpenOutlined, QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { MaaEndScriptConfig } from '@/types/script'

const props = defineProps<{
  launchMode: MaaEndScriptConfig['Game']['LaunchMode']
  source: 'auto' | 'manual'
  path: string
  error: string
  detecting: boolean
  saving: boolean
  disabled: boolean
  canDetect: boolean
  capabilitiesReady: boolean
  capabilitiesLoading: boolean
  maaEndLaunchSupported: boolean
}>()
const emit = defineEmits<{
  changeLaunchMode: [value: MaaEndScriptConfig['Game']['LaunchMode']]
  changeSource: [value: 'auto' | 'manual']
  refresh: []
  selectFile: []
}>()
const { t } = useI18n()
const usesMasLauncher = computed(() => props.launchMode !== 'MaaEnd')
const nativeLauncherHint = computed(() =>
  t(
    !props.capabilitiesReady
      ? 'edit.maaEndLaunchCapabilitiesUnknown'
      : props.maaEndLaunchSupported
        ? 'edit.maaEndNativeManualLauncherHint'
        : 'edit.maaEndNativeLauncherHint'
  )
)
const nativeLauncherHelp = computed(() =>
  !props.capabilitiesReady || !props.maaEndLaunchSupported
    ? nativeLauncherHint.value
    : t(
        props.source === 'manual'
          ? 'edit.maaEndManualLauncherHelp'
          : 'edit.maaEndNativeLauncherHelp'
      )
)
const canConfigureLauncher = computed(
  () => props.capabilitiesReady && (usesMasLauncher.value || props.maaEndLaunchSupported)
)
const launchModeOptions = computed(() => [
  { value: 'Launcher', label: t('edit.launchViaLauncher') },
  { value: 'MAS', label: t('edit.maaEndLaunchViaMas') },
  {
    value: 'MaaEnd',
    label: t('edit.maaEndLaunchViaMaaEnd'),
    disabled: !props.capabilitiesReady || !props.maaEndLaunchSupported,
  },
])
const launchHint = computed(() => {
  const description = t(
    props.launchMode === 'MaaEnd'
      ? 'edit.maaEndNativeModeHint'
      : props.launchMode === 'MAS'
        ? 'edit.maaEndMasModeHint'
        : 'edit.maaEndLauncherModeHint'
  )
  const limitation = !props.capabilitiesReady
    ? t('edit.maaEndLaunchCapabilitiesUnknown')
    : !props.maaEndLaunchSupported
      ? t('edit.maaEndNativeLaunchUnsupported')
      : ''
  return [description, limitation].filter(Boolean).join(' ')
})
const sourceOptions = computed(() => [
  {
    value: 'auto',
    label: t(
      usesMasLauncher.value ? 'edit.maaEndLauncherSourceAuto' : 'edit.maaEndLauncherSourceNative'
    ),
  },
  { value: 'manual', label: t('edit.maaEndLauncherSourceManual') },
])
</script>

<style scoped>
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.launcher-source {
  display: flex;
  align-items: center;
  margin-top: 8px;
}

.launcher-path-input {
  min-width: 0;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}
</style>
