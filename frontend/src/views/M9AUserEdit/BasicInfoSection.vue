<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.basicInfo') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="userName" required>
          <template #label>
            <a-tooltip :title="t('edit.nameUsedTellUsers')">
              <span class="form-label">
                {{ t('edit.username') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.userName"
            :placeholder="t('edit.enterUsername')"
            :disabled="loading"
            size="large"
            class="modern-input"
            @blur="emitSave('userName', formData.userName)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="status">
          <template #label>
            <a-tooltip :title="t('edit.whetherThisUserEnabled')">
              <span class="form-label">
                {{ t('edit.enabled') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Status"
            size="large"
            @change="emitSave('Info.Status', formData.Info.Status)"
          >
            <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="resource">
          <template #label>
            <a-tooltip :title="t('edit.pickGameServerThis2')">
              <span class="form-label">
                {{ t('edit.server') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Resource"
            :placeholder="t('edit.pickServer')"
            :disabled="loading"
            size="large"
            :options="resourceOptions"
            @change="emitSave('Info.Resource', formData.Info.Resource)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="account">
          <template #label>
            <a-tooltip>
              <template #title>
                <div style="max-width: 260px; white-space: normal">
                  填写目标账号时会在账号列表中逐页下滑查找并切换，找不到则任务失败<br /><br />
                  {{ t('edit.thisCurrentlyWorksCn') }}
                </div>
              </template>
              <span class="form-label">
                {{ t('edit.accountInfo') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.Info.Account"
            :placeholder="t('edit.leaveEmptySkipAccount')"
            :disabled="loading"
            size="large"
            class="modern-input"
            @blur="emitSave('Info.Account', formData.Info.Account)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="remainedDay">
          <template #label>
            <a-tooltip :title="t('edit.daysLeftAccount1')">
              <span class="form-label">
                {{ t('edit.daysLeft') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input-number
            v-model:value="formData.Info.RemainedDay"
            :min="-1"
            :max="9999"
            placeholder="0"
            :disabled="loading"
            size="large"
            style="width: 100%"
            @blur="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-form-item name="notes">
      <template #label>
        <a-tooltip :title="t('edit.addNoteAboutThis')">
          <span class="form-label">
            {{ t('edit.note') }}
            <QuestionCircleOutlined class="help-icon" />
          </span>
        </a-tooltip>
      </template>
      <a-textarea
        v-model:value="formData.Info.Notes"
        :placeholder="t('edit.enterNote3')"
        :rows="4"
        :disabled="loading"
        class="modern-input"
        @blur="emitSave('Info.Notes', formData.Info.Notes)"
      />
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const { t } = useI18n()

const resourceOptions = [
  { label: '官服', value: '官服' },
  { label: 'B 服', value: 'B 服' },
  { label: 'OPPO 服', value: 'OPPO 服' },
  { label: '小米服', value: '小米服' },
  { label: '华为服', value: '华为服' },
  { label: '国际服（EN）', value: '国际服（EN）' },
  { label: '国际服（JP）', value: '国际服（JP）' },
  { label: '港澳台服', value: '港澳台服' },
  { label: '国际服（KR）', value: '国际服（KR）' },
]

const formData = defineModel<any>('formData', { required: true })

defineProps<{
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
}

.section-header {
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: #13c2c2;
  box-shadow: 0 0 0 4px rgba(19, 194, 194, 0.15);
}
</style>
