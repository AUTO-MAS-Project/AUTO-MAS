<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <UserAccountHeading v-if="heading" :user-name="formData.userName" :options="heading" />
  <SectionCard variant="plain" :title="t('core.edit.basicInfo')" class="maafw-basic-info">
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
        <!-- 「仅本地记录」只写在占位里；特调把账号派了用场（M9A 切号 / 选号）时，作用写在标签的问号里 -->
        <a-form-item>
          <template #label>
            <a-tooltip v-if="accountRecordTooltip" :title="accountRecordTooltip">
              <span class="form-label">
                {{ t('core.edit.account') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
            <span v-else class="form-label">{{ t('core.edit.account') }}</span>
          </template>
          <a-input
            v-model:value="formData.Info.Id"
            size="large"
            autocomplete="off"
            :placeholder="accountPlaceholder || t('core.edit.localNoteOnly')"
            @blur="emitSave('Info.Id', formData.Info.Id)"
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
  </SectionCard>
</template>

<script setup lang="ts">
import UserAccountHeading from '@/components/UserAccountHeading.vue'
import UserBasicInfoFields from '@/components/UserBasicInfoFields.vue'
import { SectionCard } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
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
.maafw-basic-info {
  margin-bottom: 24px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}
</style>
