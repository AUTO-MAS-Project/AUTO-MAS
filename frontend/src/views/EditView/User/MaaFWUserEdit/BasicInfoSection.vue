<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.basicInfo') }}</h3>
    </div>

    <a-row :gutter="24">
      <a-col :xs="24" :md="8">
        <a-form-item name="userName">
          <template #label>
            <a-tooltip :title="t('edit.giveThisConfigurationName')">
              <span class="form-label">
                {{ t('edit.userName') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.userName"
            :placeholder="t('edit.enterUserName')"
            size="large"
            @blur="emitSave('Info.Name', formData.Info.Name)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="12" :md="8">
        <a-form-item :label="t('edit.enabled2')">
          <!-- 和同一行的其他控件一样用下拉，别一个开关孤零零地矮一截 -->
          <a-select
            v-model:value="statusValue"
            size="large"
            style="width: 100%"
            :options="statusOptions"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="12" :md="8">
        <a-form-item :label="t('edit.daysLeft')">
          <a-input-number
            v-model:value="formData.Info.RemainedDay"
            :min="-1"
            :max="9999"
            size="large"
            style="width: 100%"
            @blur="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :xs="24" :md="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="accountRecordTooltip">
              <span class="form-label">
                {{ t('edit.account') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.Info.Account"
            size="large"
            autocomplete="off"
            :placeholder="accountPlaceholder || t('edit.localNoteOnly')"
            @blur="emitSave('Info.Account', formData.Info.Account)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="accountRecordTooltip">
              <span class="form-label">
                {{ t('edit.password') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            v-model:value="formData.Info.Password"
            size="large"
            autocomplete="off"
            :placeholder="t('edit.localNoteOnly')"
            @blur="emitSave('Info.Password', formData.Info.Password)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item :label="t('edit.note')">
          <a-input
            v-model:value="formData.Info.Notes"
            allow-clear
            :placeholder="t('edit.enterNote2')"
            size="large"
            @blur="emitSave('Info.Notes', formData.Info.Notes)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-alert class="account-record-alert" type="info" show-icon :message="accountRecordTooltip" />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWUserConfig } from '@/types/script'

const { t } = useI18n()

type MaaFWUserFormData = MaaFWUserConfig & {
  userName: string
}

const props = defineProps<{
  formData: MaaFWUserFormData
  interfaceDependentDisabled: boolean
  accountRecordTooltip: string
  /** 账号字段占位：特调类型（M9A）把账号绑成切号任务，文案不再是「仅本地记录」 */
  accountPlaceholder?: string
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

const emitSave = (key: string, value: unknown) => {
  emit('save', key, value)
}

// 启用状态用下拉表达；a-select 的值只认字符串 / 数字，这里和布尔互转
const statusOptions = computed(() => [
  { label: t('edit.enabled3'), value: 'on' },
  { label: t('edit.disabled'), value: 'off' },
])
const statusValue = computed({
  get: () => (props.formData.Info.Status ? 'on' : 'off'),
  set: (value: string) => {
    props.formData.Info.Status = value === 'on'
    emitSave('Info.Status', props.formData.Info.Status)
  },
})
</script>

<style scoped>
.form-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.account-record-alert {
  margin-bottom: 16px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}
</style>
