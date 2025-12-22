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
          <a-select v-model:value="formData.Info.Status" size="large" @change="emitSave('Info.Status', formData.Info.Status)">
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
          <a-input-password
            v-model:value="formData.Info.Password"
            placeholder="密码仅用于储存以防遗忘，此外无任何作用"
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
            @change="emitSave('Info.RemainedDay', formData.Info.RemainedDay)"
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
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

defineProps<{
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
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
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
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}
</style>
