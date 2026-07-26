<template>
  <a-modal
    :open="open"
    :title="null"
    :footer="null"
    :width="'90vw'"
    :style="{ top: '5vh', maxWidth: '1400px' }"
    :body-style="{ padding: 0, height: '85vh' }"
    :destroy-on-close="true"
    @cancel="$emit('close')"
  >
    <div class="log-modal-content">
      <!-- 头部 -->
      <div class="modal-header">
        <div class="header-left">
          <div class="header-info">
            <FileTextOutlined class="header-icon" />
            <div class="header-text">
              <span class="header-title">详细日志</span>
              <span class="header-subtitle">{{ recordDate }}</span>
            </div>
            <a-tag :color="recordStatus === 'DONE' ? 'success' : 'error'" size="small">
              {{ recordStatus === 'DONE' ? '完成' : '失败' }}
            </a-tag>
          </div>

          <!-- 统计数据 -->
          <a-divider type="vertical" style="height: 32px; margin: 0 16px" />
          <div class="header-stats">
            <!-- 公招统计 -->
            <div
              v-if="recruitStatistics && Object.keys(recruitStatistics).length > 0"
              class="stat-group"
            >
              <span class="stat-label">公招:</span>
              <div class="stat-items">
                <span v-for="(count, star) in recruitStatistics" :key="star" class="stat-item">
                  <span class="star-text" :class="`star-${star}`">{{ star }}：</span>
                  <span class="stat-count">{{ count }}</span>
                </span>
              </div>
            </div>
            <!-- 掉落统计 -->
            <a-popover
              v-if="dropStatistics && Object.keys(dropStatistics).length > 0"
              placement="bottomLeft"
              trigger="hover"
            >
              <template #content>
                <div class="drop-popover">
                  <div v-for="(drops, stage) in dropStatistics" :key="stage" class="drop-stage">
                    <div class="stage-name">{{ stage }}</div>
                    <div class="stage-items">
                      <span v-for="(count, item) in drops" :key="item" class="drop-item">
                        {{ item }} ×{{ count }}
                      </span>
                    </div>
                  </div>
                </div>
              </template>
              <a-button size="small" class="drop-btn"> <GiftOutlined /> 查看掉落统计 </a-button>
            </a-popover>
          </div>
        </div>

        <div class="header-actions">
          <a-checkbox v-model:checked="removeEmptyLines" class="empty-lines-checkbox">
            去除空行
          </a-checkbox>
          <a-divider type="vertical" />
          <a-tooltip title="打开日志文件">
            <a-button size="small" type="text" :disabled="!hasFile" @click="$emit('open-file')">
              <template #icon>
                <FileOutlined />
              </template>
            </a-button>
          </a-tooltip>
          <a-tooltip title="打开所在目录">
            <a-button
              size="small"
              type="text"
              :disabled="!hasFile"
              @click="$emit('open-directory')"
            >
              <template #icon>
                <FolderOpenOutlined />
              </template>
            </a-button>
          </a-tooltip>
          <a-divider type="vertical" />
          <a-tooltip title="字体大小">
            <a-select
              :value="fontSize"
              size="small"
              style="width: 72px"
              :options="fontSizeOptions.map(v => ({ value: v, label: v + 'px' }))"
              @change="(v: number) => $emit('update:fontSize', v)"
            />
          </a-tooltip>
          <a-tooltip title="搜索: Ctrl+F">
            <a-button size="small" type="text">
              <template #icon>
                <SearchOutlined />
              </template>
            </a-button>
          </a-tooltip>
        </div>
      </div>

      <!-- 日志内容 -->
      <div class="modal-body">
        <a-spin :spinning="loading" style="height: 100%">
          <div v-if="logContent" class="log-editor">
            <vue-monaco-editor
              :value="displayLogContent"
              :theme="editorTheme"
              :options="monacoOptions"
              height="100%"
              language="logfile"
              @before-mount="registerLogLanguage"
            />
          </div>
          <div v-else class="empty-log">
            <LoadingOutlined v-if="loading" style="font-size: 32px" />
            <template v-else>
              <FileExclamationOutlined class="empty-icon" />
              <span class="empty-title">暂无日志内容</span>
              <span v-if="errorMessage" class="error-message">{{ errorMessage }}</span>
            </template>
          </div>
        </a-spin>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import {
  FileExclamationOutlined,
  FileOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  GiftOutlined,
  LoadingOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { computed, defineAsyncComponent, ref } from 'vue'

// 异步加载，避免 4.2 MB 的 monaco chunk 成为本路由的静态依赖。
const VueMonacoEditor = defineAsyncComponent(() =>
  import('@guolao/vue-monaco-editor').then(module => module.VueMonacoEditor)
)

interface Props {
  open: boolean
  logContent: string | null
  loading: boolean
  hasFile: boolean
  recordDate: string
  recordStatus: string
  errorMessage?: string
  recruitStatistics: Record<string, number> | null
  dropStatistics: Record<string, Record<string, number>> | null
  fontSize: number
  fontSizeOptions: number[]
  editorTheme: string
  monacoOptions: Record<string, any>
  registerLogLanguage: (monaco: any) => void
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'close'): void
  (e: 'open-file'): void
  (e: 'open-directory'): void
  (e: 'update:fontSize', value: number): void
}>()

// 去除空行开关（默认开启）
const removeEmptyLines = ref(true)

// 处理后的日志内容
const displayLogContent = computed(() => {
  if (!props.logContent) return ''
  if (!removeEmptyLines.value) return props.logContent
  // 去除空行（只包含空白字符的行也算空行）
  return props.logContent
    .split('\n')
    .filter(line => line.trim() !== '')
    .join('\n')
})

// 计算掉落物品总数
</script>

<style scoped>
.log-modal-content {
  display: flex;
  flex-direction: column;
  height: 85vh;
  background: var(--v6-color-surface);
  border-radius: var(--v6-radius-card);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--v6-space-3) var(--v6-space-5);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  background: var(--v6-color-surface);
  flex-wrap: wrap;
  gap: var(--v6-space-3);
}

.header-left {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v6-space-2);
}

.header-info {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
}

.header-icon {
  font-size: var(--v6-font-size-lg);
  color: var(--v6-color-info);
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.header-title {
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.header-subtitle {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-secondary);
}

.empty-lines-checkbox {
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
}

.header-stats {
  display: flex;
  align-items: center;
  gap: var(--v6-space-4);
}

.stat-group {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

.stat-label {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-secondary);
}

.stat-items {
  display: flex;
  gap: var(--v6-space-2);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: var(--v6-font-size-xs);
  padding: 2px var(--v6-space-1);
  background: var(--v6-vibrancy-hover);
  border-radius: var(--v6-radius-sm);
}

.star-text {
  font-weight: var(--v6-font-weight-medium);
}

.star-text.star-1,
.star-text.star-2 {
  color: var(--v6-color-text-tertiary);
}

.star-text.star-3 {
  color: var(--v6-color-info);
}

.star-text.star-4 {
  color: var(--v6-color-processing);
}

.star-text.star-5 {
  color: var(--v6-color-warning);
}

.star-text.star-6 {
  color: var(--v6-color-error);
}

.stat-count {
  color: var(--v6-color-text);
  font-weight: var(--v6-font-weight-semibold);
}

.drop-btn {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-info);
  background: var(--v6-color-info-bg);
  border: 1px solid var(--v6-color-info);
  border-radius: var(--v6-radius-sm);
  padding: 2px var(--v6-space-2);
  height: auto;
}

.drop-btn:hover {
  background: var(--v6-color-info);
  color: var(--v6-color-text-inverse);
}

.drop-popover {
  max-width: 300px;
  max-height: 300px;
  overflow-y: auto;
}

.drop-stage {
  margin-bottom: var(--v6-space-3);
}

.drop-stage:last-child {
  margin-bottom: 0;
}

.stage-name {
  font-weight: var(--v6-font-weight-semibold);
  font-size: var(--v6-font-size-sm);
  margin-bottom: var(--v6-space-1);
  color: var(--v6-color-text);
}

.stage-items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--v6-space-1);
}

.drop-item {
  font-size: var(--v6-font-size-xs);
  padding: 2px var(--v6-space-2);
  background: var(--v6-vibrancy-hover);
  border-radius: var(--v6-radius-sm);
  color: var(--v6-color-text-secondary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
}

.modal-body {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.modal-body :deep(.ant-spin-nested-loading),
.modal-body :deep(.ant-spin-container) {
  height: 100%;
}

.log-editor {
  height: 100%;
}

.log-editor :deep(.monaco-editor .margin) {
  background-color: transparent;
}

.log-editor :deep(.monaco-editor .monaco-editor-background) {
  background-color: var(--v6-color-surface);
}

.empty-log {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--v6-space-3);
  color: var(--v6-color-text-secondary);
}

.empty-icon {
  font-size: 48px;
  color: var(--v6-color-text-quaternary);
}

.empty-title {
  font-size: var(--v6-font-size-lg);
  color: var(--v6-color-text-secondary);
}

.error-message {
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-error);
  max-width: 400px;
  text-align: center;
  padding: var(--v6-space-2) var(--v6-space-4);
  background: var(--v6-color-error-bg);
  border-radius: var(--v6-radius-control);
}
</style>
