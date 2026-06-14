<!-- eslint-disable vue/no-mutating-props -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>基本信息</h3>
    </div>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="userName" required>
          <template #label>
            <span class="form-label">
              用户名
              <a-tooltip title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
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
        <a-form-item>
          <template #label>
            <span class="form-label">
              启用状态
              <a-tooltip title="是否启用该用户">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
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
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              账号ID
              <a-tooltip
                title="用于切换账号，无需切换则留空。官服输入 11 位手机号。模拟器暂不支持账号切换"
              >
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input
            v-model:value="formData.Info.Id"
            placeholder="请输入账号ID"
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
              密码
              <a-tooltip title="用户密码，PC 端需要切换账号时必须填写，模拟器暂不支持账号切换">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-password
            v-model:value="formData.Info.Password"
            placeholder="请输入密码"
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
              配置文件来源
              <a-tooltip title="脚本使用全局配置文件，用户使用当前用户的配置文件">
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
              编辑脚本设定
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
              导入
            </a-button>
          </div>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <span class="form-label">
              接管具体任务配置
              <a-tooltip
                title="开启后运行前会用本页高频配置项覆盖 MaaEnd 任务；关闭后直接运行配置文件内的完整任务配置"
              >
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
              游戏资源
              <a-tooltip title="选择当前用户使用的游戏资源">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-select
            v-model:value="formData.Info.Resource"
            placeholder="请选择资源"
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
              剩余天数
              <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
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
          备注
          <a-tooltip title="为用户添加备注信息">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </span>
      </template>
      <a-textarea
        v-model:value="formData.Info.Notes"
        placeholder="请输入备注"
        :rows="4"
        :disabled="loading"
        class="modern-input"
        @blur="emitSave('Info.Notes', formData.Info.Notes)"
      />
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import {
  EditOutlined,
  ImportOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

const emit = defineEmits<{
  save: [key: string, value: any]
  configure: []
  importConfig: []
  scriptConfig: []
}>()

defineProps<{
  formData: any
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
