<template>
  <div class="config-source-section">
    <a-row :gutter="24">
      <a-col :span="24">
        <GeneralConfigModeSelector
          :model-value="formData.Info.Base"
          :options="maaEndConfigModeOptions"
          :disabled="loading"
          :quick-config="quickConfig"
          :quick-config-disabled="quickConfigDisabled"
          :alert-message="t('core.edit.configSourceHintBase')"
          :show-gui-hint="false"
          @change="$emit('modeChange', $event)"
          @quick-config-change="$emit('quickConfigChange', $event)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="24">
        <ConfigActionsSection
          :base="formData.Info.Base"
          script-label="MaaEnd"
          :disabled="loading || showConfigMask"
          :config-loading="configLoading"
          :configuring="showConfigMask"
          :import-loading="importLoading"
          @configure="$emit('configure')"
          @import-config="$emit('importConfig')"
          @script-config="$emit('scriptConfig')"
        />
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import ConfigActionsSection from '@/views/EditView/User/ConfigActionsSection.vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'

const { t } = useI18n()
defineEmits<{
  configure: []
  importConfig: []
  scriptConfig: []
  modeChange: [value: boolean | string]
  quickConfigChange: [value: boolean]
}>()

const formData = defineModel<any>('formData', { required: true })
withDefaults(
  defineProps<{
    loading: boolean
    configLoading?: boolean
    importLoading?: boolean
    showConfigMask?: boolean
    quickConfig?: boolean | undefined
    quickConfigDisabled?: boolean | undefined
  }>(),
  { quickConfig: undefined, quickConfigDisabled: undefined }
)

// 配置来源三态卡片（value 为后端 Info.Base 取值，驱动逻辑需保持原样；文案走词表，与其它专项同一套 key）
const maaEndConfigModeOptions: Array<{
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useSharedScriptLevel'),
    icon: 'file',
  },
  {
    value: 'independent',
    title: t('core.edit.user'),
    description: t('core.edit.useThisUserS'),
    icon: 'database',
  },
  {
    value: 'native',
    title: t('core.edit.directControl'),
    description: t('core.edit.nativeConfigSourceDescription'),
    icon: 'setting',
  },
]
</script>

<style scoped>
@media (max-width: 900px) {
  .config-source-section :deep(.config-mode-options) {
    display: flex;
    flex-direction: column;
  }
  .config-source-section :deep(.config-mode-option) {
    min-height: auto;
  }
}
</style>
