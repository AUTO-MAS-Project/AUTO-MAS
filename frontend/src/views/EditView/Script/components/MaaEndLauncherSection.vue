<template>
  <a-row :gutter="24">
    <a-col :xs="24" :md="12">
      <a-form-item>
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
          @change="emit('changeLaunchMode', $event)"
        />
      </a-form-item>
    </a-col>
    <a-col v-if="launchMode === 'Launcher'" :xs="24" :md="12">
      <a-form-item :validate-status="error ? 'error' : undefined" :help="error || undefined">
        <template #label>
          <span class="form-label">{{ t('edit.maaEndLauncherPath') }}</span>
        </template>
        <a-space-compact block size="large">
          <a-input
            :value="path"
            :title="path"
            :placeholder="t('edit.maaEndPickClientBeforeLauncher')"
            :aria-label="t('edit.maaEndLauncherPath')"
            size="large"
            readonly
            class="launcher-path-input"
          />
          <a-button
            :loading="detecting || saving"
            :disabled="disabled || (source === 'auto' && !canDetect)"
            size="large"
            @click="source === 'auto' ? emit('refresh') : emit('selectFile')"
          >
            <template #icon>
              <ReloadOutlined v-if="source === 'auto'" />
              <FolderOpenOutlined v-else />
            </template>
            {{ t(source === 'auto' ? 'edit.maaEndRefreshLauncher' : 'edit.maaEndChangeLauncher') }}
          </a-button>
        </a-space-compact>
        <div class="launcher-source">
          <a-radio-group
            :value="source"
            :options="sourceOptions"
            :aria-label="t('edit.maaEndLauncherPathSource')"
            :disabled="disabled || detecting"
            @change="emit('changeSource', $event.target.value)"
          />
          <a-tooltip
            :title="
              t(source === 'auto' ? 'edit.maaEndLauncherAutoHint' : 'edit.maaEndLauncherManualHint')
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

defineProps<{
  launchMode: MaaEndScriptConfig['Game']['LaunchMode']
  source: 'auto' | 'manual'
  path: string
  error: string
  detecting: boolean
  saving: boolean
  disabled: boolean
  canDetect: boolean
}>()
const emit = defineEmits<{
  changeLaunchMode: [value: MaaEndScriptConfig['Game']['LaunchMode']]
  changeSource: [value: 'auto' | 'manual']
  refresh: []
  selectFile: []
}>()
const { t } = useI18n()
const launchModeOptions = computed(() => [
  { value: 'Client', label: t('edit.launchDirectly') },
  { value: 'Launcher', label: t('edit.launchViaLauncher') },
])
const sourceOptions = computed(() => [
  { value: 'auto', label: t('edit.maaEndLauncherSourceAuto') },
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
