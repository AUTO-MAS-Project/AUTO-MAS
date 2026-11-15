<template>
  <!-- 队列框里置顶的「全局选项」：不是任务，不能拖、不能删、没有红绿灯，也不进右键菜单 -->
  <button
    type="button"
    class="task-row global-options-row"
    :class="{ 'task-row-selected': selected }"
    :aria-pressed="selected"
    @click="emit('select')"
  >
    <ControlOutlined class="global-options-icon" aria-hidden="true" />
    <div class="task-main">
      <span class="task-title">{{ t('core.edit.maafwGlobalOptions') }}</span>
    </div>
  </button>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ControlOutlined } from '@ant-design/icons-vue'

defineProps<{
  selected: boolean
}>()

const emit = defineEmits<{
  select: []
}>()

const { t } = useI18n()
</script>

<style scoped src="./maafwQueueRow.css"></style>

<style scoped>
/* 与任务行同高：任务行尾有 32px 高的灯与上下移，这里没有，用最小高度补齐 */
.global-options-row {
  flex: none;
  justify-content: flex-start;
  min-height: 57px;
  background: var(--ant-color-fill-quaternary);
}

.global-options-row.task-row-selected {
  background: var(--ant-color-primary-bg);
}

/* 占在任务行拖拽手柄的位置上，标题与任务标题大致对齐 */
.global-options-icon {
  flex: 0 0 auto;
  padding: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 16px;
}
</style>
