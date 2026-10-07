<template>
  <!-- 预设 / 模板卡片：左图标、中间标题（预设带描述，模板带任务数与失效数）、右侧按钮，下面是任务标签串 -->
  <div class="preset-card">
    <div class="preset-card-inner">
      <div class="preset-header">
        <div class="preset-icon-wrap">
          <BookOutlined v-if="kind === 'template'" class="preset-icon" />
          <ThunderboltOutlined v-else class="preset-icon" />
        </div>
        <div class="preset-info">
          <div class="preset-title-row">
            <h3 class="preset-name">{{ title }}</h3>
            <span v-if="invalidCount" class="queue-invalid-tag">
              {{ t('edit.queueInvalidCount', { count: invalidCount }) }}
            </span>
          </div>
          <div v-if="taskCount !== undefined" class="preset-task-count">
            {{ t('edit.queueTaskCount', { count: taskCount }) }}
          </div>
          <MaaFWDescriptionView
            v-if="description && basePath !== undefined"
            :content="description"
            :base-path="basePath"
            class="preset-desc"
          />
        </div>
        <!-- 按钮就放在标题右边，不再单占一行 -->
        <div class="preset-actions">
          <slot name="actions" />
        </div>
      </div>
      <MaaFWQueueChips :chips="chips" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BookOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import MaaFWDescriptionView from '../MaaFWDescriptionView.vue'
import MaaFWQueueChips from './MaaFWQueueChips.vue'

defineProps<{
  /** 项目预设用闪电图标，自定义模板用书本图标 */
  kind: 'preset' | 'template'
  title: string
  /** 预设的描述（interface 里写的，可能带图片，按项目目录解析） */
  description?: string | null
  basePath?: string
  /** 模板：「N 个任务」 */
  taskCount?: number
  /** 模板：已失效的任务数，0 不显示 */
  invalidCount?: number
  chips: ReadonlyArray<{ id: string; label: string; invalid?: boolean }>
}>()

const { t } = useI18n()
</script>

<style scoped>
.preset-card {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.preset-card-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

.preset-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.preset-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  flex: 0 0 auto;
}

.preset-icon {
  font-size: 18px;
}

.preset-info {
  flex: 1;
  min-width: 0;
}

.preset-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.preset-name {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 16px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.preset-task-count {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.preset-desc {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 与图标同高（36px）、靠右，不随描述换行下坠 */
.preset-actions {
  display: flex;
  flex: 0 0 auto;
  align-self: flex-start;
  gap: 8px;
}

.preset-actions :deep(.ant-btn) {
  height: 36px;
}

/* 「N 个已失效」：虚线灰标签 */
.queue-invalid-tag {
  flex: none;
  padding: 0 7px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}
</style>
