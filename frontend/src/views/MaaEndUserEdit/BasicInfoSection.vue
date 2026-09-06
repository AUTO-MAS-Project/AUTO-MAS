<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.basicInfo') }}</h3>
    </div>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="userName" required>
          <template #label>
            <span class="form-label">
              {{ t('edit.username') }}
              <a-tooltip :title="t('edit.nameUsedTellUsers')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
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
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.enabled') }}
              <a-tooltip :title="t('edit.whetherThisUserEnabled')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
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
            v-model:value="formData.Info.Id"
            :placeholder="t('edit.enterAccountId')"
            :disabled="loading"
            size="large"
            @blur="emitSave('Info.Id', formData.Info.Id)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
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
            v-model:value="formData.Info.Password"
            :placeholder="t('edit.passwordStoredOnlySo2')"
            :disabled="loading"
            size="large"
            @blur="emitSave('Info.Password', formData.Info.Password)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="24">
        <GeneralConfigModeSelector
          :model-value="formData.Info.Mode"
          :options="maaEndConfigModeOptions"
          :disabled="loading"
          alert-message="脚本使用脚本级共享配置，用户使用当前用户独立配置；直控直接使用 MaaEnd 原有配置。接管具体任务配置是独立覆盖层。"
          @change="$emit('modeChange', $event)"
        />
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('edit.configurationSource')">
          <div class="config-source-control">
            <a-button
              type="primary"
              ghost
              size="large"
              :loading="configLoading"
              :disabled="loading || showConfigMask"
              @click="$emit('configure')"
            >
              <template #icon>
                <SettingOutlined />
              </template>
              {{ showConfigMask ? '正在配置' : `配置${currentConfigModeLabel}` }}
            </a-button>
            <a-button
              v-if="formData.Info.Mode !== '直控'"
              type="default"
              size="large"
              :loading="importLoading"
              :disabled="loading || showConfigMask"
              @click="$emit('importConfig')"
            >
              <template #icon>
                <ImportOutlined />
              </template>
              {{ t('edit.import2') }}
            </a-button>
            <a-button
              type="default"
              size="large"
              :disabled="loading || showConfigMask"
              @click="$emit('scriptConfig')"
            >
              <template #icon>
                <EditOutlined />
              </template>
              {{ t('edit.editScriptSettings') }}
            </a-button>
          </div>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.takeOverTaskConfiguration') }}
              <a-tooltip :title="t('edit.whenHighTrafficSettings')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-select
            v-model:value="formData.Info.IfQuickConfig"
            size="large"
            :disabled="loading || presetSupported === false"
            :options="quickConfigOptions"
            @change="emitSave('Info.IfQuickConfig', formData.Info.IfQuickConfig)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.gameResource') }}
              <a-tooltip :title="t('edit.pickGameResourceThis')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-select
            v-model:value="formData.Info.Resource"
            :placeholder="t('edit.pickResource')"
            :disabled="loading"
            size="large"
            :options="resourceOptions"
            @change="emitSave('Info.Resource', formData.Info.Resource)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
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
            v-model:value="formData.Info.RemainedDay"
            :min="-1"
            :max="9999"
            :disabled="loading"
            size="large"
            style="width: 100%"
            @blur="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-form-item>
      <template #label>
        <span class="form-label">
          {{ t('edit.note') }}
          <a-tooltip :title="t('edit.addNoteAboutThis')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </span>
      </template>
      <a-textarea
        v-model:value="formData.Info.Notes"
        :placeholder="t('edit.enterNote')"
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
import {
  EditOutlined,
  ImportOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { computed } from 'vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'

const { t } = useI18n()
const emit = defineEmits<{
  save: [key: string, value: any]
  configure: []
  importConfig: []
  scriptConfig: []
  modeChange: [value: boolean | string]
}>()

const formData = defineModel<any>('formData', { required: true })
defineProps<{
  loading: boolean
  resourceOptions: Array<{ label: string; value: string }>
  presetSupported?: boolean
  configLoading?: boolean
  importLoading?: boolean
  showConfigMask?: boolean
}>()

const maaEndConfigModeOptions: Array<{
  value: '脚本' | '用户' | '直控'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    value: '脚本',
    title: '脚本',
    description: '使用脚本级共享配置，所有用户共用。',
    icon: 'file',
  },
  {
    value: '用户',
    title: '用户',
    description: '使用当前用户独立配置，与脚本配置隔离。',
    icon: 'database',
  },
  {
    value: '直控',
    title: '直控',
    description: '直接使用 MaaEnd 原有配置，由 MaaEnd GUI 维护。',
    icon: 'setting',
  },
]

const quickConfigOptions = [
  { label: t('edit.enabled3'), value: true },
  { label: t('edit.off'), value: false },
]

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const currentConfigModeLabel = computed(() => {
  if (formData.value.Info.Mode === '直控') return '脚本直控'
  if (formData.value.Info.Mode === '用户') return '用户独立'
  return '脚本共享'
})
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.config-source-control {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
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
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
}
</style>
