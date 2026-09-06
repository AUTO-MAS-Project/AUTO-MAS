<template>
  <div class="form-section">
    <div class="section-header">
      <h3>基本信息</h3>
    </div>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="userName" required>
          <template #label>
            <a-tooltip title="用于识别用户的显示名称">
              <span class="form-label">用户名 <QuestionCircleOutlined class="help-icon" /></span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.userName"
            placeholder="请输入用户名"
            :disabled="loading"
            size="large"
            @blur="emitSave('userName', formData.userName)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="status">
          <template #label>
            <span class="form-label">启用状态 <QuestionCircleOutlined class="help-icon" /></span>
          </template>
          <a-select
            v-model:value="formData.Info.Status"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.Status', formData.Info.Status)"
          >
            <a-select-option :value="true">是</a-select-option>
            <a-select-option :value="false">否</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="remainedDay">
          <template #label>
            <span class="form-label">剩余天数 <QuestionCircleOutlined class="help-icon" /></span>
          </template>
          <a-input-number
            v-model:value="formData.Info.RemainedDay"
            :min="-1"
            :max="9999"
            :disabled="loading"
            size="large"
            style="width: 100%"
            @blur="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="configMode">
          <template #label>
            <a-tooltip title="用户独立配置会复制到脚本运行前；脚本直控直接使用上游原配置">
              <span class="form-label">配置来源 <QuestionCircleOutlined class="help-icon" /></span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.IfUseMasConfig"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.IfUseMasConfig', formData.Info.IfUseMasConfig)"
          >
            <a-select-option :value="true">用户独立配置</a-select-option>
            <a-select-option :value="false">脚本直控配置</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <a-form-item name="notes">
      <template #label>
        <span class="form-label">备注 <QuestionCircleOutlined class="help-icon" /></span>
      </template>
      <a-textarea
        v-model:value="formData.Info.Notes"
        placeholder="请输入备注信息"
        :rows="4"
        :disabled="loading"
        @blur="emitSave('Info.Notes', formData.Info.Notes)"
      />
    </a-form-item>

    <!-- TODO(specialized): 在这里加入专项用户字段，并让 AutoProxy 消费它们。 -->
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

interface BasicInfoFormData {
  userName: string
  Info: {
    Name: string
    Status: boolean
    RemainedDay: number
    IfUseMasConfig: boolean
    Notes: string
  }
}

const props = defineProps<{
  formData: BasicInfoFormData
  loading: boolean
}>()
const loading = computed(() => props.loading)

const formData = reactive<BasicInfoFormData>({
  userName: props.formData.userName,
  Info: { ...props.formData.Info },
})

watch(
  () => props.formData,
  value => {
    formData.userName = value.userName
    Object.assign(formData.Info, value.Info)
  },
  { deep: true }
)

const emit = defineEmits<{
  save: [key: string, value: string | number | boolean]
}>()

const emitSave = (key: string, value: string | number | boolean) => {
  emit('save', key, value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  padding-left: 12px;
  border-left: 4px solid var(--ant-color-primary);
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text);
  font-weight: 500;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}
</style>
