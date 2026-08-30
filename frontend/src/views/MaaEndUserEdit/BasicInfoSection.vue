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
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.configurationSource') }}
              <a-tooltip :title="t('edit.scriptUsesGlobalConfiguration')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <div class="config-source-control">
            <a-select
              v-model:value="formData.Info.Mode"
              size="large"
              :options="modeOptions"
              :disabled="loading"
              @change="emitSave('Info.Mode', formData.Info.Mode)"
            />
            <a-button
              v-if="formData.Info.Mode === '简洁'"
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
            <a-button
              v-else
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
              {{ showConfigMask ? '正在配置' : '配置' }}
            </a-button>
            <a-button
              v-if="formData.Info.Mode !== '简洁'"
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

const { t } = useI18n()
const emit = defineEmits<{
  save: [key: string, value: any]
  configure: []
  importConfig: []
  scriptConfig: []
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

const modeOptions = [
  { label: '脚本', value: '简洁' },
  { label: '用户', value: '详细' },
]

const quickConfigOptions = [
  { label: '启用', value: true },
  { label: '关闭', value: false },
]

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.config-source-control {
  display: flex;
  gap: 8px;
}

.config-source-control :deep(.ant-select) {
  flex: 1;
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
