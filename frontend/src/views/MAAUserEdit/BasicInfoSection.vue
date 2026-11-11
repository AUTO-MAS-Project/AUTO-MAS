<template>
  <div class="form-section">
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
      <a-col :span="12">
        <a-form-item name="userId">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.accountId')"
              :hint="t('core.edit.usedSwitchAccountsCn')"
              variant="form"
            />
          </template>
          <a-input
            v-model:value="formData.userId"
            :placeholder="t('core.edit.enterAccountId')"
            :disabled="loading"
            size="large"
            @blur="emitSave('userId', formData.userId)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item :name="['Info', 'Password']">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.password')"
              :hint="t('core.edit.userSPasswordStored')"
              variant="form"
            />
          </template>
          <a-input-password
            v-model:value="formData.Info.Password"
            :placeholder="t('core.edit.passwordStoredOnlySo')"
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
    </a-row>
  </div>
</template>

<script setup lang="ts">
import accountIcon from '@/assets/MAA.png'
import UserAccountHeading from '@/components/UserAccountHeading.vue'
import type { UserAccountHeadingOptions } from '@/types/userEditor'
import UserBasicInfoFields from '@/components/UserBasicInfoFields.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const formData = defineModel<any>('formData', { required: true })

defineProps<{
  heading?: Omit<UserAccountHeadingOptions, 'logoSrc'>
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

<style scoped></style>
