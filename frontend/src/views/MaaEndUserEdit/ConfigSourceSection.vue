<template>
  <div class="config-source-section">
    <a-row :gutter="24">
      <a-col :span="24">
        <GeneralConfigModeSelector
          :model-value="formData.Info.Mode"
          :options="maaEndConfigModeOptions"
          :disabled="loading"
          :alert-message="t('edit.configSourceHintBase')"
          @change="$emit('modeChange', $event)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="24">
        <a-form-item :label="t('edit.maaEndConfigActions')">
          <div class="config-source-control">
            <a-button
              type="primary"
              ghost
              :loading="configLoading"
              :disabled="loading || showConfigMask"
              @click="$emit('configure')"
            >
              <template #icon>
                <SettingOutlined />
              </template>
              {{
                showConfigMask
                  ? t('edit.maaEndConfiguring')
                  : t('edit.maaEndConfigureSource', { source: currentConfigModeLabel })
              }}
            </a-button>
            <a-button
              v-if="formData.Info.Mode !== '直控'"
              type="default"
              :loading="importLoading"
              :disabled="loading || showConfigMask"
              @click="$emit('importConfig')"
            >
              <template #icon>
                <ImportOutlined />
              </template>
              {{ t('edit.import2') }}
            </a-button>
            <a-button
              type="default"
              :disabled="loading || showConfigMask"
              @click="$emit('scriptConfig')"
            >
              <template #icon>
                <EditOutlined />
              </template>
              {{ t('edit.editScriptSettings') }}
            </a-button>
          </div>
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { EditOutlined, ImportOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'

const { t } = useI18n()
defineEmits<{
  configure: []
  importConfig: []
  scriptConfig: []
  modeChange: [value: boolean | string]
}>()

const formData = defineModel<any>('formData', { required: true })
defineProps<{
  loading: boolean
  configLoading?: boolean
  importLoading?: boolean
  showConfigMask?: boolean
}>()

const maaEndConfigModeOptions: Array<{
  value: '脚本' | '用户' | '直控'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    value: '脚本',
    title: '脚本',
    description: '使用脚本级共享配置，所有用户共用。',
    icon: 'file',
  },
  {
    value: '用户',
    title: '用户',
    description: '使用当前用户独立配置，与脚本配置隔离。',
    icon: 'database',
  },
  {
    value: '直控',
    title: '直控',
    description: '直接使用 MaaEnd 原有配置，由 MaaEnd GUI 维护。',
    icon: 'setting',
  },
]

const currentConfigModeLabel = computed(() => {
  if (formData.value.Info.Mode === '直控') return '脚本直控'
  if (formData.value.Info.Mode === '用户') return '用户独立'
  return '脚本共享'
})
</script>

<style scoped>
.config-source-control {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.config-source-section :deep(.ant-form-item:last-child) {
  margin-bottom: 0;
}
</style>
