<template>
  <div class="form-section">
    <div v-if="!hideSectionHeader" class="section-header">
      <h3>{{ t('comp.extraScripts') }}</h3>
    </div>
    <a-form-item name="scriptBeforeTask">
      <template #label>
        <a-tooltip
          :title="
            t(scope === 'queue' ? 'queue.runCustomScriptBefore' : 'comp.runCustomScriptBefore')
          "
        >
          <span class="form-label">
            {{ t(scope === 'queue' ? 'queue.runScriptBefore' : 'comp.runScriptBeforeTask') }}
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
          <PathPickerField
            v-model="formData.Info.ScriptBeforeTask"
            mode="file"
            :placeholder="t('comp.pickScriptFile')"
            :pick-label="t('comp.pickFile')"
            :disabled="loading || !formData.Info.IfScriptBeforeTask"
            @pick="selectScriptBeforeTask"
          />
        </a-col>
      </a-row>
    </a-form-item>
    <a-form-item name="scriptAfterTask">
      <template #label>
        <a-tooltip
          :title="t(scope === 'queue' ? 'queue.runCustomScriptAfter' : 'comp.runCustomScriptAfter')"
        >
          <span class="form-label">
            {{ t(scope === 'queue' ? 'queue.runScriptAfter' : 'comp.runScriptAfterTask') }}
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
          <PathPickerField
            v-model="formData.Info.ScriptAfterTask"
            mode="file"
            :placeholder="t('comp.pickScriptFile')"
            :pick-label="t('comp.pickFile')"
            :disabled="loading || !formData.Info.IfScriptAfterTask"
            @pick="selectScriptAfterTask"
          />
        </a-col>
      </a-row>
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import PathPickerField from '@/components/PathPickerField.vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('额外脚本配置')

const formData = defineModel<any>('formData', { required: true })
const props = defineProps<{
  loading: boolean
  scope?: 'task' | 'queue'
  // 卡片化页面（如 MaaEnd 用户编辑页）由外层卡片提供标题时隐藏内部标题
  hideSectionHeader?: boolean
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
      message.success(
        t(props.scope === 'queue' ? 'queue.preTaskScriptPath' : 'comp.preTaskScriptPath')
      )
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
      message.success(
        t(props.scope === 'queue' ? 'queue.postTaskScriptPath' : 'comp.postTaskScriptPath')
      )
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
</style>
