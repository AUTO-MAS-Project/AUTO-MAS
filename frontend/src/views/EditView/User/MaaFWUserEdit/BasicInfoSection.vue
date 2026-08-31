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
      <a-col :xs="12" :md="4">
        <a-form-item :label="t('edit.enabled2')">
          <a-switch
            v-model:checked="formData.Info.Status"
            :checked-children="t('edit.enabled3')"
            :un-checked-children="t('edit.disabled')"
            @change="emitSave('Info.Status', formData.Info.Status)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="12" :md="6">
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
      <a-col :xs="24" :md="6">
        <a-form-item :label="t('edit.applyPreset')">
          <a-dropdown
            trigger="click"
            :disabled="interfaceDependentDisabled || presetOptions.length === 0"
          >
            <a-button
              size="large"
              block
              class="preset-switch-button"
              :disabled="interfaceDependentDisabled || presetOptions.length === 0"
            >
              <span>{{ selectedPresetLabel }}</span>
              <DownOutlined />
            </a-button>
            <template #overlay>
              <a-menu
                :selected-keys="formData.Task.SelectedPreset ? [formData.Task.SelectedPreset] : []"
                @click="(event: MenuInfo) => emit('presetMenuClick', event)"
              >
                <a-menu-item v-for="item in presetOptions" :key="item.name">
                  {{ getDisplayName(item) }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
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
            :placeholder="t('edit.localNoteOnly')"
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
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'
import { DownOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWPresetInfo, MaaFWUserConfig } from '@/types/script'

const { t } = useI18n()

type MaaFWUserFormData = MaaFWUserConfig & {
  userName: string
}

type DisplayItem = {
  name: string
  label?: string | null
}

defineProps<{
  formData: MaaFWUserFormData
  presetOptions: MaaFWPresetInfo[]
  selectedPresetLabel: string
  interfaceDependentDisabled: boolean
  accountRecordTooltip: string
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
  presetMenuClick: [event: MenuInfo]
}>()

const getDisplayName = (item: DisplayItem) => item.label || item.name

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
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
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

.preset-switch-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.preset-switch-button span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}
</style>
