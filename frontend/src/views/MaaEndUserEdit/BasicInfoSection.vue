<template>
  <div class="basic-info-section">
    <a-row :gutter="24">
      <a-col :xs="24" :sm="24" :md="8">
        <a-form-item name="userName" required>
          <template #label>
            <span class="form-label">
              {{ t('edit.username') }}
            </span>
          </template>
          <a-input
            size="large"
            v-model:value="formData.userName"
            :placeholder="t('edit.enterUsername')"
            :disabled="loading"
            @blur="emitSave('userName', formData.userName)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="12" :md="8">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.daysLeft') }}
              <a-tooltip :title="t('edit.daysLeftAccount1')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-number
            size="large"
            v-model:value="formData.Info.RemainedDay"
            :min="-1"
            :max="9999"
            :disabled="loading"
            style="width: 100%"
            @blur="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="12" :md="8">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.enabled') }}
            </span>
          </template>
          <a-select
            v-model:value="formData.Info.Status"
            :disabled="loading"
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
      <a-col :xs="24" :sm="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.accountId') }}
              <a-tooltip :title="t('edit.usedSwitchAccountsCn2')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input
            size="large"
            v-model:value="formData.Info.Id"
            :placeholder="t('edit.enterAccountId')"
            :disabled="loading"
            @blur="emitSave('Info.Id', formData.Info.Id)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.password') }}
              <a-tooltip :title="t('edit.userSPasswordStored')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-password
            size="large"
            v-model:value="formData.Info.Password"
            :placeholder="t('edit.passwordStoredOnlySo2')"
            :disabled="loading"
            @blur="emitSave('Info.Password', formData.Info.Password)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row v-if="showResource" :gutter="24">
      <a-col v-if="showResource" :xs="24" :sm="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.gameResource') }}
            </span>
          </template>
          <a-select
            size="large"
            v-model:value="formData.Info.Resource"
            :placeholder="t('edit.pickResource')"
            :disabled="loading"
            :options="resourceOptions"
            @change="emitSave('Info.Resource', formData.Info.Resource)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-form-item>
      <template #label>
        <span class="form-label">
          {{ t('edit.note') }}
        </span>
      </template>
      <a-textarea
        v-model:value="formData.Info.Notes"
        :placeholder="t('edit.enterNote')"
        :auto-size="{ minRows: 2, maxRows: 4 }"
        :disabled="loading"
        @blur="emitSave('Info.Notes', formData.Info.Notes)"
      />
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const { t } = useI18n()
const emit = defineEmits<{ save: [key: string, value: any] }>()
const formData = defineModel<any>('formData', { required: true })
defineProps<{
  loading: boolean
  showResource: boolean
  resourceOptions: Array<{ label: string; value: string }>
}>()

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
