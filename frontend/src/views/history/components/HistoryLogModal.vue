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
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { computed, ref } from 'vue'

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
const dropCount = computed(() => {
  if (!props.dropStatistics) return 0
  let count = 0
  for (const stage of Object.values(props.dropStatistics)) {
    count += Object.keys(stage).length
  }
  return count
})
</script>

<style scoped>
.log-modal-content {
  display: flex;
  flex-direction: column;
  height: 85vh;
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  font-size: 20px;
  color: var(--ant-color-primary);
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.header-subtitle {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.empty-lines-checkbox {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.header-stats {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-label {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.stat-items {
  display: flex;
  gap: 8px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  padding: 2px 6px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
}

.star-text {
  font-weight: 500;
}

.star-text.star-1,
.star-text.star-2 {
  color: #8c8c8c;
}

.star-text.star-3 {
  color: #1890ff;
}

.star-text.star-4 {
  color: #722ed1;
}

.star-text.star-5 {
  color: #faad14;
}

.star-text.star-6 {
  color: #f5222d;
}

.stat-count {
  color: var(--ant-color-text);
  font-weight: 600;
}

.drop-btn {
  font-size: 12px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  border: 1px solid var(--ant-color-primary);
  border-radius: 4px;
  padding: 2px 8px;
  height: auto;
}

.drop-btn:hover {
  background: var(--ant-color-primary);
  color: #fff;
}

.drop-popover {
  max-width: 300px;
  max-height: 300px;
  overflow-y: auto;
}

.drop-stage {
  margin-bottom: 12px;
}

.drop-stage:last-child {
  margin-bottom: 0;
}

.stage-name {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 6px;
  color: var(--ant-color-text);
}

.stage-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.drop-item {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
  color: var(--ant-color-text-secondary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
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
  background-color: var(--ant-color-bg-container);
}

.empty-log {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--ant-color-text-secondary);
}

.empty-icon {
  font-size: 48px;
  color: var(--ant-color-text-quaternary);
}

.empty-title {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
}

.error-message {
  font-size: 13px;
  color: var(--ant-color-error);
  max-width: 400px;
  text-align: center;
  padding: 8px 16px;
  background: var(--ant-color-error-bg);
  border-radius: 6px;
}
</style>
