<template>
  <div class="maa-preset-editor">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('comp.maaPresetEditor.title') }}</h1>
        <p class="page-description">{{ t('comp.maaPresetEditor.description') }}</p>
      </div>
      <a-space wrap>
        <a-tag :color="isDirty ? 'gold' : 'green'">
          {{ isDirty ? t('comp.maaPresetEditor.unsaved') : t('comp.maaPresetEditor.saved') }}
        </a-tag>
        <a-button :loading="loading" :disabled="saving" @click="reloadPreset">
          {{ t('comp.maaPresetEditor.reload') }}
        </a-button>
        <a-button :disabled="loading || saving" @click="formatPreset">
          {{ t('comp.maaPresetEditor.format') }}
        </a-button>
        <a-button :loading="saving" type="primary" :disabled="!isDirty" @click="savePreset">
          {{ t('comp.maaPresetEditor.save') }}
        </a-button>
      </a-space>
    </div>

    <a-alert
      v-if="loadError"
      class="state-alert"
      type="error"
      show-icon
      :message="loadError"
      :description="t('comp.maaPresetEditor.loadErrorHint')"
      closable
      @close="loadError = ''"
    />
    <a-alert
      v-if="validationError"
      class="state-alert"
      type="error"
      show-icon
      :message="t('comp.maaPresetEditor.invalidJson')"
      :description="validationError"
    />
    <a-alert
      v-if="saveError"
      class="state-alert"
      type="error"
      show-icon
      :message="saveError"
      closable
      @close="saveError = ''"
    />

    <a-card class="editor-card" :body-style="{ padding: 0 }">
      <a-spin :spinning="loading" :tip="t('comp.maaPresetEditor.loading')">
        <div class="editor-container">
          <vue-monaco-editor
            v-model:value="source"
            language="json"
            :theme="editorTheme"
            :options="editorOptions"
            class="preset-editor"
            @mount="handleEditorMount"
            @validate="handleMarkers"
          />
        </div>
      </a-spin>
    </a-card>

    <div class="editor-footer">
      <span
        >{{ t('comp.maaPresetEditor.pathLabel') }}: {{ sourcePath || t('common.unknown') }}</span
      >
      <span v-if="markerCount > 0" class="marker-hint">
        {{ t('comp.maaPresetEditor.markerCount', { count: markerCount }) }}
      </span>
      <span class="footer-hint">{{ t('comp.maaPresetEditor.footerHint') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { useMaaBasePresetApi } from '@/composables/useMaaBasePresetApi'

defineOptions({ name: 'MaaPresetEditor' })

type JsonObject = Record<string, unknown>

const { t } = useI18n()
const { isDark } = useTheme()
const { loading, saving, getBasePreset, saveBasePreset } = useMaaBasePresetApi()

const source = ref('')
const savedSource = ref('')
const sourcePath = ref('')
const loadError = ref('')
const saveError = ref('')
const validationError = ref('')
const markerCount = ref(0)

const isDirty = computed(() => source.value !== savedSource.value)
const editorTheme = computed(() => (isDark.value ? 'vs-dark' : 'vs'))
const editorOptions = {
  automaticLayout: true,
  formatOnPaste: true,
  formatOnType: true,
  insertSpaces: true,
  lineNumbers: 'on',
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  tabSize: 2,
  wordWrap: 'off',
} as const

let editorInstance: {
  getAction?: (id: string) => { run: () => Promise<void> } | undefined
} | null = null

const parseSource = (): JsonObject | null => {
  try {
    const parsed: unknown = JSON.parse(source.value)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(t('comp.maaPresetEditor.rootObjectRequired'))
    }
    validationError.value = ''
    return parsed as JsonObject
  } catch (error) {
    validationError.value = error instanceof Error ? error.message : String(error)
    return null
  }
}

const formatSource = (value: JsonObject): string => `${JSON.stringify(value, null, 2)}\n`

const applyResponse = (data: JsonObject, path?: string) => {
  const formatted = formatSource(data)
  source.value = formatted
  savedSource.value = formatted
  sourcePath.value = path || ''
  validationError.value = ''
  saveError.value = ''
}

const loadPreset = async () => {
  loadError.value = ''
  try {
    const response = await getBasePreset()
    if (!response.data) throw new Error(t('comp.maaPresetEditor.emptyResponse'))
    applyResponse(response.data, response.path)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
  }
}

const confirmDiscard = () =>
  new Promise<boolean>(resolve => {
    Modal.confirm({
      title: t('comp.maaPresetEditor.discardTitle'),
      content: t('comp.maaPresetEditor.discardContent'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })

const reloadPreset = async () => {
  if (isDirty.value && !(await confirmDiscard())) return
  await loadPreset()
}

const savePreset = async () => {
  const parsed = parseSource()
  if (!parsed) return

  saveError.value = ''
  try {
    const response = await saveBasePreset(parsed)
    if (!response.data) throw new Error(t('comp.maaPresetEditor.emptyResponse'))
    applyResponse(response.data, response.path || sourcePath.value)
    message.success(t('comp.maaPresetEditor.saveSuccess'))
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : String(error)
  }
}

const formatPreset = async () => {
  const parsed = parseSource()
  if (!parsed) return
  source.value = formatSource(parsed)
  await editorInstance?.getAction?.('editor.action.formatDocument')?.run()
  message.success(t('comp.maaPresetEditor.formatSuccess'))
}

const handleEditorMount = (editor: typeof editorInstance) => {
  editorInstance = editor
}

const handleMarkers = (markers: unknown[]) => {
  markerCount.value = markers.length
}

const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  if (!isDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => (isDirty.value ? confirmDiscard() : true))

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  void loadPreset()
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<style scoped>
.maa-preset-editor {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 24px;
  font-weight: 600;
}

.page-description {
  margin: 6px 0 0;
  color: var(--ant-color-text-secondary);
}

.state-alert {
  margin-bottom: 12px;
}

.editor-card {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.editor-card :deep(.ant-card-body),
.editor-card :deep(.ant-spin-nested-loading),
.editor-card :deep(.ant-spin-container) {
  height: 100%;
  min-height: 0;
}

.editor-container {
  height: 100%;
  min-height: 360px;
  overflow: hidden;
}

.preset-editor {
  height: 100%;
  min-height: 360px;
}

.editor-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  margin-top: 10px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.marker-hint {
  color: var(--ant-color-error);
}

.footer-hint {
  margin-left: auto;
}
</style>
