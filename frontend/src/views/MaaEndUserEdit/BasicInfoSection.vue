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
              <a-tooltip
                title="用户密码（加密存储）。PC 端切换账号时需要填写；模拟器暂不支持账号切换。留空保持原值，输入新值替换，点击“清空原值”清空"
              >
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <div class="sensitive-field-row">
            <a-input-password
              :value="passwordDraft"
              :placeholder="passwordPlaceholder"
              :disabled="loading"
              size="large"
              autocomplete="new-password"
              @update:value="(val: string) => handlePasswordInput(val)"
              @blur="handlePasswordBlur"
            />
            <a-button
              v-if="!loading && hasStoredPassword"
              size="small"
              type="link"
              danger
              :disabled="passwordExplicitlyCleared"
              @click="handleClearPassword"
            >
              {{ passwordExplicitlyCleared ? '已清空' : '清空原值' }}
            </a-button>
          </div>
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
import { computed, ref, watch } from 'vue'
import {
  EditOutlined,
  ImportOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

const props = defineProps<{
  formData: any
  loading: boolean
  resourceOptions: Array<{ label: string; value: string }>
  presetSupported?: boolean
  configLoading?: boolean
  importLoading?: boolean
  showConfigMask?: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
  /**
   * 敏感字段保存意图（Lane 06 任务书第 2 条）。
   *
   * - `keep`：用户未触碰密码字段，不发送给后端（保持原密文）。
   * - `replace`：用户输入了新明文，发送给后端（后端加密为新密文）。
   * - `clear`：用户点击“清空原值”，发送空串 `""` 给后端（后端加密为空密文）。
   */
  sensitiveSave: [key: string, intent: 'keep' | 'replace' | 'clear', value?: string]
  /** 敏感字段 dirty 状态变更；父组件用于 useUnsavedChangesGuard.isDirty。 */
  sensitiveDirtyChange: [key: string, dirty: boolean]
  configure: []
  importConfig: []
  scriptConfig: []
}>()

const modeOptions = [
  { label: '脚本', value: '简洁' },
  { label: '用户', value: '详细' },
]

const quickConfigOptions = [
  { label: '启用', value: true },
  { label: '关闭', value: false },
]

// ============================================================
// 密码字段：草稿驱动，不在 DOM 显示明文（Lane 06 任务书第 1 条）
// ============================================================

/** 密码草稿：用户在 input 中输入的内容；初始空串，不回显后端解密的明文。 */
const passwordDraft = ref('')

/** 用户是否显式点击“清空原值”。 */
const passwordExplicitlyCleared = ref(false)

/** 后端是否已存储密码（modelValue 中 Info.Password 非空）。 */
const hasStoredPassword = computed(() => {
  const stored = props.formData?.Info?.Password
  return typeof stored === 'string' && stored.length > 0
})

/** DOM 占位文本：根据后端是否已存储和显式清空状态切换。 */
const passwordPlaceholder = computed(() => {
  if (passwordExplicitlyCleared.value) {
    return '已清空。留空保持清空状态，输入新值替换'
  }
  if (hasStoredPassword.value) {
    return '已保存。留空保持原值，输入新值替换'
  }
  return '请输入密码'
})

/**
 * 用户在密码字段输入时：
 * - 更新本地草稿（不写回 formData.Info.Password，避免明文进入 DOM/modelValue）。
 * - 重新输入时撤销“显式清空”意图（替换优先于清空）。
 * - 通知父组件 dirty 状态变更。
 */
const handlePasswordInput = (val: string) => {
  passwordDraft.value = val
  if (val !== '' && passwordExplicitlyCleared.value) {
    passwordExplicitlyCleared.value = false
  }
  emit('sensitiveDirtyChange', 'Info.Password', val !== '' || passwordExplicitlyCleared.value)
}

/**
 * 用户点击“清空原值”按钮：
 * - 把草稿置空。
 * - 设置 explicitCleared = true，下次 blur 时发送 clear 意图。
 */
const handleClearPassword = () => {
  if (!hasStoredPassword.value) {
    return
  }
  passwordDraft.value = ''
  passwordExplicitlyCleared.value = true
  emit('sensitiveDirtyChange', 'Info.Password', true)
}

/**
 * blur 时按真实后端保存协议发送意图：
 * - 草稿为空且未显式清空 → `keep`（不发送给后端，保持原密文）。
 * - 草稿非空 → `replace`（发送新明文，后端加密为新密文）。
 * - 显式清空 → `clear`（发送空串 `""`，后端加密为空密文）。
 */
const handlePasswordBlur = () => {
  if (passwordExplicitlyCleared.value) {
    emit('sensitiveSave', 'Info.Password', 'clear', '')
    // 后端处理完成后父组件应调用 resetPasswordDraft。
    return
  }
  if (passwordDraft.value === '') {
    // 未输入也未清空：保持原值，不发送给后端。
    emit('sensitiveSave', 'Info.Password', 'keep')
    return
  }
  emit('sensitiveSave', 'Info.Password', 'replace', passwordDraft.value)
}

/**
 * 父组件在保存成功 / 权威 reload 后调用：清空草稿与 explicitCleared。
 *
 * 通过 watch formData.Info.Password 实现：后端 reload 后 Password 字段更新（可能是新密文解密后的明文），
 * 此时草稿失去意义，必须清空。
 */
watch(
  () => props.formData?.Info?.Password,
  () => {
    passwordDraft.value = ''
    passwordExplicitlyCleared.value = false
    emit('sensitiveDirtyChange', 'Info.Password', false)
  }
)

// 通用字段：保持原有的 @blur → emit('save') 模式
const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

/**
 * 暴露给父组件：手动重置密码草稿。
 * 父组件在 useUnsavedChangesGuard 离开确认或表单 reset 后调用。
 */
defineExpose({
  resetPasswordDraft: () => {
    passwordDraft.value = ''
    passwordExplicitlyCleared.value = false
  },
  isPasswordDirty: () => passwordDraft.value !== '' || passwordExplicitlyCleared.value,
})
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

.sensitive-field-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.sensitive-field-row :deep(.ant-input-password) {
  width: 100%;
}

.sensitive-field-row :deep(.ant-btn-link) {
  padding: 0;
  height: auto;
  font-size: 12px;
  line-height: 1.5;
}
</style>
