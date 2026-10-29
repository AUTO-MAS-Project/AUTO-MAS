<template>
  <a-row :gutter="24">
    <a-col :xs="24" :md="12">
      <a-form-item :help="launchHint">
        <template #label>
          <FieldLabelWithHint
            :text="t('core.edit.launchType')"
            :hint="t('core.edit.maaEndLaunchTypeHint')"
            variant="form"
          />
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
          <span class="form-label">{{ t('core.edit.maaEndLauncherPath') }}</span>
        </template>
        <a-space-compact v-if="usesMasLauncher || source === 'manual'" block size="large">
          <a-input
            :value="path"
            :title="path"
            :placeholder="
              t(
                usesMasLauncher
                  ? 'core.edit.maaEndPickClientBeforeLauncher'
                  : 'core.edit.maaEndLauncherSourceNative'
              )
            "
            :aria-label="t('core.edit.maaEndLauncherPath')"
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
                  ? 'core.edit.maaEndRefreshLauncher'
                  : 'core.edit.maaEndChangeLauncher'
              )
            }}
          </a-button>
        </a-space-compact>
        <div class="launcher-source">
          <a-radio-group
            :value="source"
            :options="sourceOptions"
            :aria-label="t('core.edit.maaEndLauncherPathSource')"
            :disabled="disabled || detecting || !canConfigureLauncher"
            @change="emit('changeSource', $event.target.value)"
          />
          <a-tooltip
            :title="
              !usesMasLauncher
                ? nativeLauncherHint
                : t(
                    source === 'auto'
                      ? 'core.edit.maaEndLauncherAutoHint'
                      : 'core.edit.maaEndLauncherManualHint'
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
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
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
      ? 'core.edit.maaEndLaunchCapabilitiesUnknown'
      : props.maaEndLaunchSupported
        ? 'core.edit.maaEndNativeManualLauncherHint'
        : 'core.edit.maaEndNativeLauncherHint'
  )
)
const nativeLauncherHelp = computed(() =>
  !props.capabilitiesReady || !props.maaEndLaunchSupported
    ? nativeLauncherHint.value
    : t(
        props.source === 'manual'
          ? 'core.edit.maaEndManualLauncherHelp'
          : 'core.edit.maaEndNativeLauncherHelp'
      )
)
const canConfigureLauncher = computed(
  () => props.capabilitiesReady && (usesMasLauncher.value || props.maaEndLaunchSupported)
)
const recommendedLabel = (name: string, native: boolean) =>
  props.capabilitiesReady && props.maaEndLaunchSupported === native
    ? t('core.edit.maaEndRecommendedLaunch', { name })
    : name
const launchModeOptions = computed(() => {
  const options = [
    { value: 'Launcher', label: t('core.edit.launchViaLauncher') },
    { value: 'MAS', label: recommendedLabel(t('core.edit.maaEndLaunchViaMas'), false) },
    {
      value: 'MaaEnd',
      label: recommendedLabel(t('core.edit.maaEndLaunchViaMaaEnd'), true),
      disabled: !props.capabilitiesReady || !props.maaEndLaunchSupported,
    },
  ]
  if (!props.capabilitiesReady) return options
  const recommended = props.maaEndLaunchSupported ? 'MaaEnd' : 'MAS'
  return options.sort(
    (left, right) => Number(right.value === recommended) - Number(left.value === recommended)
  )
})
const launchHint = computed(() => {
  const description = t(
    props.launchMode === 'MaaEnd'
      ? 'core.edit.maaEndNativeModeHint'
      : props.launchMode === 'MAS'
        ? 'core.edit.maaEndMasModeHint'
        : 'core.edit.maaEndLauncherModeHint'
  )
  const limitation = !props.capabilitiesReady
    ? t('core.edit.maaEndLaunchCapabilitiesUnknown')
    : !props.maaEndLaunchSupported
      ? t('core.edit.maaEndNativeLaunchUnsupported')
      : ''
  return [description, limitation].filter(Boolean).join(' ')
})
const sourceOptions = computed(() => [
  {
    value: 'auto',
    label: t(
      usesMasLauncher.value
        ? 'core.edit.maaEndLauncherSourceAuto'
        : 'core.edit.maaEndLauncherSourceNative'
    ),
  },
  { value: 'manual', label: t('core.edit.maaEndLauncherSourceManual') },
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
