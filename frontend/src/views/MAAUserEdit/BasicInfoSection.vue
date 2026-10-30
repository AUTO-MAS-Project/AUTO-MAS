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
        <UserStatusField
          name="status"
          v-model="formData.Info.Status"
          :hint="t('core.edit.whetherThisUserEnabled')"
          :disabled="loading"
          @save="emitSave('Info.Status', formData.Info.Status)"
        />
      </a-col>
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

      <a-col :span="12">
        <UserRemainedDayField
          name="remainedDay"
          v-model="formData.Info.RemainedDay"
          :hint="t('core.edit.daysLeftAccount1')"
          placeholder="0"
          :disabled="loading"
          @save="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
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

<style scoped></style>
