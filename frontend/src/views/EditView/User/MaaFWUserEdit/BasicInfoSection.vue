<template>
  <div class="form-section">
    <div class="section-header">
      <h3>基本信息</h3>
    </div>

    <a-row :gutter="24">
      <a-col :xs="24" :md="8">
        <a-form-item name="userName">
          <template #label>
            <a-tooltip title="为当前配置设置一个易于识别的名称">
              <span class="form-label">
                用户名称
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.userName"
            placeholder="请输入用户名称…"
            size="large"
            @blur="emitSave('Info.Name', formData.Info.Name)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="12" :md="4">
        <a-form-item label="启用">
          <a-switch
            v-model:checked="formData.Info.Status"
            checked-children="启用"
            un-checked-children="禁用"
            @change="emitSave('Info.Status', formData.Info.Status)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="12" :md="6">
        <a-form-item label="剩余天数">
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
        <a-form-item label="一键切换预设">
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
                账号
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.Info.Account"
            size="large"
            autocomplete="off"
            placeholder="仅用于本地记录…"
            @blur="emitSave('Info.Account', formData.Info.Account)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="accountRecordTooltip">
              <span class="form-label">
                密码
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <div class="sensitive-field">
            <a-input-password
              :value="passwordDraft"
              size="large"
              autocomplete="new-password"
              :placeholder="passwordPlaceholder"
              @update:value="updatePasswordDraft"
            />
            <a-space>
              <a-button type="primary" ghost :disabled="!passwordDraft" @click="savePassword">
                保存新值
              </a-button>
              <a-button v-if="hasStoredPassword" danger @click="clearPassword">清空原值</a-button>
            </a-space>
          </div>
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item label="备注">
          <a-input
            v-model:value="formData.Info.Notes"
            allow-clear
            placeholder="请输入备注…"
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
import { computed, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'
import { DownOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWPresetInfo, MaaFWUserConfig } from '@/types/script'

type MaaFWUserFormData = MaaFWUserConfig & {
  userName: string
}

type DisplayItem = {
  name: string
  label?: string | null
}

const props = defineProps<{
  formData: MaaFWUserFormData
  presetOptions: MaaFWPresetInfo[]
  selectedPresetLabel: string
  interfaceDependentDisabled: boolean
  accountRecordTooltip: string
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
  sensitiveSave: [key: 'Info.Password', intent: 'replace' | 'clear', value?: string]
  sensitiveDirtyChange: [key: 'Info.Password', dirty: boolean]
  presetMenuClick: [event: MenuInfo]
}>()

const passwordDraft = ref('')
const hasStoredPassword = computed(() => Boolean(props.formData.Info.Password))
const passwordPlaceholder = computed(() =>
  hasStoredPassword.value ? '已保存；输入新值后明确保存' : '仅用于本地记录…'
)

const updatePasswordDraft = (value: string) => {
  passwordDraft.value = value
  emit('sensitiveDirtyChange', 'Info.Password', Boolean(value))
}

const savePassword = () => {
  if (!passwordDraft.value) return
  emit('sensitiveSave', 'Info.Password', 'replace', passwordDraft.value)
}

const clearPassword = () => {
  Modal.confirm({
    title: '清空已保存密码？',
    content: '清空后无法恢复，后续如需账号切换必须重新填写。',
    okText: '清空',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => emit('sensitiveSave', 'Info.Password', 'clear', ''),
  })
}

defineExpose({
  resetPasswordDraft: () => {
    passwordDraft.value = ''
    emit('sensitiveDirtyChange', 'Info.Password', false)
  },
})

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

.sensitive-field {
  display: grid;
  gap: var(--v6-space-2);
}
</style>
