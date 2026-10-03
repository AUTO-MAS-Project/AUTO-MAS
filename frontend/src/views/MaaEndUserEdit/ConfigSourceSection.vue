<template>
  <div class="config-source-section">
    <a-row :gutter="24">
      <a-col :span="24">
        <GeneralConfigModeSelector
          :model-value="formData.Info.Mode"
          :options="maaEndConfigModeOptions"
          :disabled="loading"
          :quick-config="quickConfig"
          :quick-config-disabled="quickConfigDisabled"
          :alert-message="t('edit.configSourceHintBase')"
          @change="$emit('modeChange', $event)"
          @quick-config-change="$emit('quickConfigChange', $event)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="24">
        <a-form-item :label="t('edit.maaEndConfigActions')">
          <div class="config-source-control">
            <a-tooltip v-if="formData.Info.Mode !== '直控'" :title="maaEndOpenConfigTip">
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
                {{ showConfigMask ? t('edit.maaEndConfiguring') : t('edit.maaEndOpenConfig') }}
              </a-button>
            </a-tooltip>
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

// 配置来源三态卡片（value 为后端 Info.Mode 取值，驱动逻辑需保持原样；文案走词表，与其它专项同一套 key）
const maaEndConfigModeOptions: Array<{
  value: '脚本' | '用户' | '直控'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    value: '脚本',
    title: t('edit.script'),
    description: t('edit.useSharedScriptLevel'),
    icon: 'file',
  },
  {
    value: '用户',
    title: t('edit.user'),
    description: t('edit.useThisUserS'),
    icon: 'database',
  },
  {
    value: '直控',
    title: t('edit.directControl'),
    description: t('edit.nativeConfigSourceDescription'),
    icon: 'setting',
  },
]

// 入口只说「打开 MaaEnd 配置界面」，共享/独立的范围放进提示，避免「配置共享/配置独立」这种抽象说法。
const maaEndOpenConfigTip = computed(() =>
  formData.value.Info.Mode === '用户'
    ? t('edit.maaEndOpenConfigIndependentTip')
    : t('edit.maaEndOpenConfigSharedTip')
)
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
