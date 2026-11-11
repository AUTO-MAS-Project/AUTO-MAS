<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
    <UserAccountHeading v-if="heading" :user-name="formData.userName" :options="heading" />
    <div class="section-header">
      <h3>{{ t('core.edit.basicInfo') }}</h3>
    </div>

    <UserBasicInfoFields
      v-model:user-name="formData.userName"
      v-model:status="formData.Info.Status"
      v-model:remained-day="formData.Info.RemainedDay"
      v-model:notes="formData.Info.Notes"
      @save-name="emitSave('Info.Name', formData.Info.Name)"
      @save-days="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
      @save-notes="emitSave('Info.Notes', formData.Info.Notes)"
      @save-status="emitSave('Info.Status', formData.Info.Status)"
    />

    <a-row :gutter="24">
      <a-col :xs="24" :md="8">
        <!-- 账号 / 密码的说明只在下面的提示框里写一次，标签上不再挂同一句的问号 -->
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.account') }}</span>
          </template>
          <a-input
            v-model:value="formData.Info.Account"
            size="large"
            autocomplete="off"
            :placeholder="accountPlaceholder || t('core.edit.localNoteOnly')"
            @blur="emitSave('Info.Account', formData.Info.Account)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.password') }}</span>
          </template>
          <a-input-password
            v-model:value="formData.Info.Password"
            size="large"
            autocomplete="off"
            :placeholder="t('core.edit.localNoteOnly')"
            @blur="emitSave('Info.Password', formData.Info.Password)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-alert class="account-record-alert" type="info" show-icon :message="accountRecordTooltip" />
  </div>
</template>

<script setup lang="ts">
import UserAccountHeading from '@/components/UserAccountHeading.vue'
import UserBasicInfoFields from '@/components/UserBasicInfoFields.vue'
import { useI18n } from 'vue-i18n'
import type {
  MaaFWUserBasicInfoSectionEmits,
  MaaFWUserBasicInfoSectionProps,
} from '../../MaaFWFlavor/sectionContracts'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
defineProps<MaaFWUserBasicInfoSectionProps>()

const emit = defineEmits<MaaFWUserBasicInfoSectionEmits>()

const emitSave = (key: string, value: unknown) => {
  emit('save', key, value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 16px;
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
