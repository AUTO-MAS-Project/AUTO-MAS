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
        <a-form-item :name="['Info', 'Id']">
          <template #label>
            <a-tooltip>
              <template #title>
                <div style="max-width: 520px; line-height: 1.6; white-space: normal">
                  用于切换账号，无需切换则留空。<br />
                  {{ t('edit.cnServersEnter11') }}
                  位手机号，若输入手机号中包含「*」则切换账号时将仅通过识别已登录账号列表登录。<br />
                  {{ t('edit.bilibiliEnterPartUsername') }}
                  {{ t('edit.accountEmailPhoneNumber2') }}
                  {{ t('edit.accountEmailPhoneNumber') }}
                </div>
              </template>
              <span class="form-label">
                {{ t('edit.accountId') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.Info.Id"
            :placeholder="t('edit.enterAccount')"
            :disabled="loading"
            size="large"
            @blur="emitSave('Info.Id', formData.Info.Id)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :name="['Info', 'Password']">
          <template #label>
            <a-tooltip :title="t('edit.userSPasswordWhen')">
              <span class="form-label">
                {{ t('edit.password') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            v-model:value="formData.Info.Password"
            :placeholder="t('edit.enterPassword')"
            :disabled="loading"
            size="large"
            @blur="emitSave('Info.Password', formData.Info.Password)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="server">
          <template #label>
            <a-tooltip :title="t('edit.pickGameServerThis')">
              <span class="form-label">
                {{ t('edit.server') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Server"
            :placeholder="t('edit.pickServer')"
            :disabled="loading"
            :options="serverOptions"
            size="large"
            @change="emitSave('Info.Server', formData.Info.Server)"
          />
        </a-form-item>
      </a-col>
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
            placeholder="-1"
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
        <a-form-item name="mode">
          <template #label>
            <a-tooltip :title="t('edit.simpleModeFollowsScript')">
              <span class="form-label">
                {{ t('edit.userConfigurationMode') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Mode"
            :options="[
              { label: t('edit.simple'), value: '简洁' },
              { label: t('edit.detailed'), value: '详细' },
            ]"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.Mode', formData.Info.Mode)"
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

const formData = defineModel<any>('formData', { required: true })

defineProps<{
  loading: boolean
  serverOptions: any[]
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
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
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
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}
</style>
