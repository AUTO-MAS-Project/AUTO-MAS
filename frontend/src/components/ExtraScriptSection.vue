<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('comp.extraScripts') }}</h3>
    </div>
    <a-form-item name="scriptBeforeTask">
      <template #label>
        <a-tooltip :title="t('comp.runCustomScriptBefore')">
          <span class="form-label">
            {{ t('comp.runScriptBeforeTask') }}
            <QuestionCircleOutlined class="help-icon" />
          </span>
        </a-tooltip>
      </template>
      <a-row :gutter="24" align="middle">
        <a-col :span="4">
          <a-switch
            v-model:checked="formData.Info.IfScriptBeforeTask"
            :disabled="loading"
            size="default"
            @change="emitSave('Info.IfScriptBeforeTask', formData.Info.IfScriptBeforeTask)"
          />
        </a-col>
        <a-col :span="20">
          <a-input-group compact class="path-input-group">
            <a-input
              v-model:value="formData.Info.ScriptBeforeTask"
              :placeholder="t('comp.pickScriptFile')"
              :disabled="loading || !formData.Info.IfScriptBeforeTask"
              size="large"
              class="path-input"
              readonly
            />
            <a-button
              size="large"
              :disabled="loading || !formData.Info.IfScriptBeforeTask"
              class="path-button"
              @click="selectScriptBeforeTask"
            >
              <template #icon>
                <FileOutlined />
              </template>
              {{ t('comp.pickFile') }}
            </a-button>
          </a-input-group>
        </a-col>
      </a-row>
    </a-form-item>
    <a-form-item name="scriptAfterTask">
      <template #label>
        <a-tooltip :title="t('comp.runCustomScriptAfter')">
          <span class="form-label">
            {{ t('comp.runScriptAfterTask') }}
            <QuestionCircleOutlined class="help-icon" />
          </span>
        </a-tooltip>
      </template>
      <a-row :gutter="24" align="middle">
        <a-col :span="4">
          <a-switch
            v-model:checked="formData.Info.IfScriptAfterTask"
            :disabled="loading"
            size="default"
            @change="emitSave('Info.IfScriptAfterTask', formData.Info.IfScriptAfterTask)"
          />
        </a-col>
        <a-col :span="20">
          <a-input-group compact class="path-input-group">
            <a-input
              v-model:value="formData.Info.ScriptAfterTask"
              :placeholder="t('comp.pickScriptFile')"
              :disabled="loading || !formData.Info.IfScriptAfterTask"
              size="large"
              class="path-input"
              readonly
            />
            <a-button
              size="large"
              :disabled="loading || !formData.Info.IfScriptAfterTask"
              class="path-button"
              @click="selectScriptAfterTask"
            >
              <template #icon>
                <FileOutlined />
              </template>
              {{ t('comp.pickFile') }}
            </a-button>
          </a-input-group>
        </a-col>
      </a-row>
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FileOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('额外脚本配置')

const formData = defineModel<any>('formData', { required: true })
defineProps<{
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const selectScriptBeforeTask = async () => {
  try {
    const path = await window.electronAPI?.selectFile([
      { name: t('comp.executables'), extensions: ['exe', 'bat', 'cmd', 'ps1'] },
      { name: t('comp.scriptFiles'), extensions: ['py', 'js', 'sh'] },
      { name: t('comp.allFiles'), extensions: ['*'] },
    ])

    if (path && path.length > 0) {
      formData.value.Info.ScriptBeforeTask = path[0]
      message.success(t('comp.preTaskScriptPath'))
      emitSave('Info.ScriptBeforeTask', path[0])
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择任务前脚本失败: ${errorMsg}`)
    message.error(t('comp.couldNotPickFile'))
  }
}

const selectScriptAfterTask = async () => {
  try {
    const path = await window.electronAPI?.selectFile([
      { name: t('comp.executables'), extensions: ['exe', 'bat', 'cmd', 'ps1'] },
      { name: t('comp.scriptFiles'), extensions: ['py', 'js', 'sh'] },
      { name: t('comp.allFiles'), extensions: ['*'] },
    ])

    if (path && path.length > 0) {
      formData.value.Info.ScriptAfterTask = path[0]
      message.success(t('comp.postTaskScriptPath'))
      emitSave('Info.ScriptAfterTask', path[0])
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择任务后脚本失败: ${errorMsg}`)
    message.error(t('comp.couldNotPickFile'))
  }
}
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
}

.section-header {
  margin-bottom: 24px;
  padding-bottom: 12px;
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

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
  transition: all 0.3s ease;
}

.path-input-group:hover {
  border-color: var(--ant-color-primary-hover);
}

.path-input-group:focus-within {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px var(--ant-color-primary-bg);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
  background: var(--ant-color-bg-container) !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.path-button:hover {
  background: var(--ant-color-primary);
  color: white;
}
</style>
