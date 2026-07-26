<template>
  <div class="form-section">
    <div class="section-header">
      <h3>基本信息</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="userName" required>
          <template #label>
            <a-tooltip title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计">
              <span class="form-label">
                用户名
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.userName"
            placeholder="请输入用户名"
            :disabled="loading"
            size="large"
            class="modern-input"
            @blur="emitSave('userName', formData.userName)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="userId">
          <template #label>
            <a-tooltip title="用于切换账号，官服输入手机号，B服输入B站ID，无需切换则留空">
              <span class="form-label">
                账号ID
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.userId"
            placeholder="请输入账号ID"
            :disabled="loading"
            size="large"
            @blur="emitSave('userId', formData.userId)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="status">
          <template #label>
            <a-tooltip title="是否启用该用户">
              <span class="form-label">
                启用状态
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Status"
            size="large"
            @change="emitSave('Info.Status', formData.Info.Status)"
          >
            <a-select-option :value="true">是</a-select-option>
            <a-select-option :value="false">否</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :name="['Info', 'Password']">
          <template #label>
            <a-tooltip title="用户密码，仅用于存储以防遗忘，此外无任何作用">
              <span class="form-label">
                密码
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div class="sensitive-field">
            <a-input-password
              :value="passwordDraft"
              :placeholder="passwordPlaceholder"
              :disabled="loading"
              size="large"
              autocomplete="new-password"
              @update:value="passwordDraft = $event"
            />
            <div class="sensitive-actions">
              <span class="sensitive-hint">原值不会回显，也不会因浏览表单被重复提交</span>
              <a-space size="small">
                <a-button
                  v-if="hasStoredPassword"
                  size="small"
                  danger
                  :disabled="loading"
                  @click="clearPassword"
                >
                  清空原值
                </a-button>
                <a-button
                  type="primary"
                  size="small"
                  :disabled="loading || !passwordDraft"
                  @click="savePassword"
                >
                  保存新值
                </a-button>
              </a-space>
            </div>
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="server">
          <template #label>
            <a-tooltip title="选择用户所在的游戏服务器">
              <span class="form-label">
                服务器
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Server"
            placeholder="请选择服务器"
            :disabled="loading"
            :options="serverOptions"
            size="large"
            @change="emitSave('Info.Server', formData.Info.Server)"
          />
        </a-form-item>
      </a-col>

      <a-col :span="12">
        <a-form-item name="remainedDay">
          <template #label>
            <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
              <span class="form-label">
                剩余天数
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input-number
            v-model:value="formData.Info.RemainedDay"
            :min="-1"
            :max="9999"
            placeholder="0"
            :disabled="loading"
            size="large"
            style="width: 100%"
            @blur="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="简洁模式下配置沿用脚本全局配置，详细模式下沿用用户自定义配置">
              <span class="form-label">
                用户配置模式
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Mode"
            :options="[
              { label: '简洁', value: '简洁' },
              { label: '详细', value: '详细' },
            ]"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.Mode', formData.Info.Mode)"
          />
        </a-form-item>
      </a-col>

      <a-col :span="12">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="选择基建模式，自定义基建模式需要自行选择自定义基建配置文件">
              <span class="form-label">
                基建模式
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.InfrastMode"
            :options="[
              { label: '常规模式', value: 'Normal' },
              { label: '一键轮休', value: 'Rotation' },
              { label: '自定义基建', value: 'Custom' },
            ]"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.InfrastMode', formData.Info.InfrastMode)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 自定义基建配置文件选择 -->
    <a-row v-if="formData.Info.InfrastMode === 'Custom'" :gutter="24">
      <a-col :span="12">
        <a-form-item name="infrastructureConfigFile">
          <template #label>
            <a-tooltip title="自定义基建配置名称与描述">
              <span class="form-label">
                自定义基建名称
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div style="display: flex; gap: 12px; align-items: center">
            <a-input
              v-model:value="formData.Info.InfrastName"
              placeholder="自定义基建名称"
              readonly
              size="large"
              style="flex: 1"
            />
            <a-button
              type="primary"
              :disabled="loading || !isEdit"
              :loading="infrastructureImporting"
              size="large"
              @click="$emit('selectAndImportInfrastructureConfig')"
            >
              选择并导入
            </a-button>
          </div>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="infrastructureIndex">
          <template #label>
            <a-tooltip title="从已导入的基建配置中选择当前的排班">
              <span class="form-label">
                自定义基建排班
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.InfrastIndex"
            placeholder="请选择自定义基建排班"
            :disabled="loading"
            :loading="infrastructureOptionsLoading"
            :options="infrastructureOptions"
            size="large"
            @change="emitSave('Info.InfrastIndex', formData.Info.InfrastIndex)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-form-item name="notes">
      <template #label>
        <a-tooltip title="为用户添加备注信息">
          <span class="form-label">
            备注
            <QuestionCircleOutlined class="help-icon" />
          </span>
        </a-tooltip>
      </template>
      <a-textarea
        v-model:value="formData.Info.Notes"
        placeholder="请输入备注信息"
        :rows="4"
        :disabled="loading"
        class="modern-input"
        @blur="emitSave('Info.Notes', formData.Info.Notes)"
      />
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const props = defineProps<{
  formData: any
  loading: boolean
  serverOptions: any[]
  infrastructureConfigPath: string
  infrastructureImporting: boolean
  infrastructureOptions: Array<{ label: string; value: string }>
  infrastructureOptionsLoading: boolean
  isEdit: boolean
}>()

const emit = defineEmits<{
  selectAndImportInfrastructureConfig: []
  save: [key: string, value: any]
  sensitiveSave: [key: 'Info.Password', intent: 'replace' | 'clear', value?: string]
}>()

const passwordDraft = ref('')
const hasStoredPassword = computed(() => Boolean(props.formData?.Info?.Password))
const passwordPlaceholder = computed(() =>
  hasStoredPassword.value ? '已保存；留空保持原值，输入新值后明确保存' : '请输入密码'
)

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const savePassword = () => {
  if (!passwordDraft.value) return
  emit('sensitiveSave', 'Info.Password', 'replace', passwordDraft.value)
}

const clearPassword = () => {
  Modal.confirm({
    title: '清空已保存密码？',
    content: '该操作会明确清空已保存的密码，不影响其他用户配置。',
    okText: '清空',
    cancelText: '取消',
    okType: 'danger',
    centered: true,
    onOk: () => emit('sensitiveSave', 'Info.Password', 'clear', ''),
  })
}

defineExpose({
  resetPasswordDraft: () => {
    passwordDraft.value = ''
  },
})
</script>

<style scoped>
.form-section {
  margin-bottom: var(--v6-space-4);
}

.section-header {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-base);
}

.help-icon {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-base);
  cursor: help;
  transition: color var(--v6-motion-fast) var(--v6-ease-out);
}

.help-icon:hover {
  color: var(--v6-color-info);
}

.modern-input {
  border-radius: var(--v6-radius-md);
  border: 1px solid var(--v6-color-border);
  background: var(--v6-color-surface);
}

.modern-input:hover {
  border-color: var(--v6-color-info);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--v6-color-info);
  box-shadow: var(--v6-shadow-focus-ring);
}

.sensitive-field {
  display: grid;
  gap: var(--v6-space-2);
}

.sensitive-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
}

.sensitive-hint {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}

@media (max-width: 768px) {
  .sensitive-actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
