<template>
  <div class="basic-info-section">
    <UserAccountHeading
      v-if="heading"
      :user-name="formData.userName"
      :options="{ ...heading, logoSrc: accountIcon }"
    />
    <div class="section-header">
      <h3>{{ t('core.edit.basicInfo') }}</h3>
    </div>
    <UserBasicInfoFields
      v-model:user-name="formData.userName"
      v-model:status="formData.Info.Status"
      v-model:remained-day="formData.Info.RemainedDay"
      v-model:notes="formData.Info.Notes"
      :disabled="loading"
      @save-name="emitSave('userName', formData.userName)"
      @save-status="emitSave('Info.Status', formData.Info.Status)"
      @save-days="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
      @save-notes="emitSave('Info.Notes', formData.Info.Notes)"
    />

    <a-row :gutter="24">
      <a-col :xs="24" :sm="12" :md="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.accountId')"
              :hint="t('core.edit.usedSwitchAccountsCn2')"
              variant="form"
            />
          </template>
          <a-input
            v-model:value="formData.Info.Id"
            :placeholder="t('core.edit.enterAccountId')"
            :disabled="loading"
            @blur="emitSave('Info.Id', formData.Info.Id)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="12" :md="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.password')"
              :hint="t('core.edit.userSPasswordStored')"
              variant="form"
            />
          </template>
          <a-input-password
            v-model:value="formData.Info.Password"
            :placeholder="t('core.edit.passwordStoredOnlySo2')"
            :disabled="loading"
            @blur="emitSave('Info.Password', formData.Info.Password)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="24" :md="8">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('core.edit.collectNodeDetails') }}
              <a-tooltip :mouse-enter-delay="0.5" :title="t('core.edit.collectsKeyMomentsFrom')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-select
            v-model:value="formData.Notify.PushLogMode"
            :options="pushLogModeOptions"
            :disabled="loading"
            @change="emitSave('Notify.PushLogMode', formData.Notify.PushLogMode)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row v-if="showResource" :gutter="24">
      <a-col :xs="24" :sm="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('core.edit.gameResource') }}
            </span>
          </template>
          <a-select
            :value="
              formData.Info.Resource === '官服' &&
              resourceOptions.some(option => option.value === 'CN')
                ? 'CN'
                : formData.Info.Resource
            "
            :placeholder="t('core.edit.pickResource')"
            :disabled="loading"
            :options="resourceOptions"
            @change="handleResourceChange"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import accountIcon from '@/assets/MaaEnd.png'
import UserAccountHeading from '@/components/UserAccountHeading.vue'
import type { UserAccountHeadingOptions } from '@/types/userEditor'
import UserBasicInfoFields from '@/components/UserBasicInfoFields.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const { t } = useI18n()
const emit = defineEmits<{ save: [key: string, value: any] }>()
const formData = defineModel<any>('formData', { required: true })
defineProps<{
  heading?: Omit<UserAccountHeadingOptions, 'logoSrc'>
  loading: boolean
  showResource: boolean
  resourceOptions: Array<{ label: string; value: string }>
}>()

// 节点详情推送模式（value 为后端 Notify.PushLogMode 取值，驱动逻辑需保持原样；label 走词表）
const pushLogModeOptions = [
  { label: t('core.edit.pushLogModeOff'), value: '关闭' },
  { label: t('core.edit.pushLogModeList'), value: '逐条' },
  { label: t('core.edit.pushLogModeSummary'), value: '汇总' },
]

const handleResourceChange = (value: string) => {
  formData.value.Info.Resource = value
  emitSave('Info.Resource', value)
}

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}
</script>

<style scoped>
.basic-info-section :deep(.ant-form-item) {
  margin-bottom: 16px;
}
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}
</style>
