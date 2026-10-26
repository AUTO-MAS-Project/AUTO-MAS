<template>
  <a-row :gutter="fullWidth ? 0 : 24">
    <a-col :span="fullWidth ? 24 : 8">
      <a-form-item>
        <template #label>
          <a-space size="small">
            {{ t('edit.hardTimeoutMinutes') }}
            <a-tooltip :title="t('edit.hardTimeoutHint')">
              <QuestionCircleOutlined />
            </a-tooltip>
          </a-space>
        </template>
        <a-input-number
          v-model:value="value"
          :min="1"
          :max="9999"
          :precision="0"
          size="large"
          style="width: 100%"
          @blur="handleSave"
        />
      </a-form-item>
    </a-col>
  </a-row>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

const value = defineModel<number>('value', { required: true })
defineProps<{ fullWidth?: boolean }>()
const emit = defineEmits<{ save: [] }>()
const { t } = useI18n()

const handleSave = () => {
  // 清空输入时恢复默认时限，避免保存空值后界面与实际运行限制不一致。
  if (value.value == null) value.value = 120
  emit('save')
}
</script>
