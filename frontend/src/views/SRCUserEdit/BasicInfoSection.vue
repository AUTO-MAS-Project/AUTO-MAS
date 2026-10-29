<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('core.edit.basicInfo') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="12">
        <UserNameField
          name="userName"
          required
          v-model="formData.userName"
          :hint="t('core.edit.nameUsedTellUsers')"
          :placeholder="t('core.edit.enterUsername')"
          :disabled="loading"
          enhanced
          @save="emitSave('userName', formData.userName)"
        />
      </a-col>
      <a-col :span="12">
        <UserStatusField
          name="status"
          v-model="formData.Info.Status"
          :hint="t('core.edit.whetherThisUserEnabled')"
          @save="emitSave('Info.Status', formData.Info.Status)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item :name="['Info', 'Id']">
          <template #label>
            <a-tooltip>
              <template #title>
                <div style="max-width: 520px; line-height: 1.6; white-space: normal">
                  {{ t('core.edit.srcAccountSwitchTipIntro') }}<br />
                  {{ t('core.edit.cnServersEnter11') }}<br />
                  {{ t('core.edit.bilibiliEnterPartUsername') }}
                  {{ t('core.edit.accountEmailPhoneNumber2') }}
                </div>
              </template>
              <span class="form-label">
                {{ t('core.edit.accountId') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.Info.Id"
            :placeholder="t('core.edit.enterAccount')"
            :disabled="loading"
            size="large"
            @blur="emitSave('Info.Id', formData.Info.Id)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :name="['Info', 'Password']">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.password')"
              :hint="t('core.edit.userSPasswordWhen')"
              variant="form"
            />
          </template>
          <a-input-password
            v-model:value="formData.Info.Password"
            :placeholder="t('core.edit.enterPassword')"
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
            <FieldLabelWithHint
              :text="t('core.edit.server')"
              :hint="t('core.edit.pickGameServerThis')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Info.Server"
            :placeholder="t('core.edit.pickServer')"
            :disabled="loading"
            :options="serverOptions"
            size="large"
            @change="emitSave('Info.Server', formData.Info.Server)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <UserRemainedDayField
          name="remainedDay"
          v-model="formData.Info.RemainedDay"
          :hint="t('core.edit.daysLeftAccount1')"
          placeholder="-1"
          :disabled="loading"
          @save="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="24">
        <GeneralConfigModeSelector
          :model-value="formData.Info.Base"
          :options="srcConfigModeOptions"
          :disabled="loading"
          :saving="quickConfigDisabled"
          :quick-config="quickConfig"
          :quick-config-disabled="quickConfigDisabled"
          :alert-message="t('core.edit.configSourceHintBase')"
          @change="emit('modeChange', $event)"
          @quick-config-change="emit('quickConfigChange', $event)"
        />
      </a-col>
    </a-row>

    <UserNotesField
      name="notes"
      v-model="formData.Info.Notes"
      :hint="t('core.edit.addNoteAboutThis')"
      :placeholder="t('core.edit.enterNote3')"
      :disabled="loading"
      :rows="4"
      enhanced
      @save="emitSave('Info.Notes', formData.Info.Notes)"
    />
  </div>
</template>

<script setup lang="ts">
import UserNameField from '@/views/EditView/User/components/UserNameField.vue'
import UserNotesField from '@/views/EditView/User/components/UserNotesField.vue'
import UserRemainedDayField from '@/views/EditView/User/components/UserRemainedDayField.vue'
import UserStatusField from '@/views/EditView/User/components/UserStatusField.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'

const { t } = useI18n()

const formData = defineModel<any>('formData', { required: true })

withDefaults(
  defineProps<{
    loading: boolean
    serverOptions: any[]
    quickConfig?: boolean | undefined
    quickConfigDisabled?: boolean | undefined
  }>(),
  { quickConfig: undefined, quickConfigDisabled: undefined }
)

// 配置来源三态卡片（value 为后端 Info.Base 取值，驱动逻辑需保持原样；文案走词表）
const srcConfigModeOptions: Array<{
  label: string
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    label: t('core.edit.script'),
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useSharedScriptLevel'),
    icon: 'file',
  },
  {
    label: t('core.edit.user'),
    value: 'independent',
    title: t('core.edit.user'),
    description: t('core.edit.useThisUserS'),
    icon: 'database',
  },
  {
    label: t('core.edit.directControl'),
    value: 'native',
    title: t('core.edit.directControl'),
    description: t('core.edit.nativeConfigSourceDescription'),
    icon: 'setting',
  },
]

const emit = defineEmits<{
  save: [key: string, value: any]
  modeChange: [value: boolean | string]
  quickConfigChange: [value: boolean]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}
</script>

<style scoped>
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
</style>
