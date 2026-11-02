<template>
  <!-- 任务标签串：预设 / 模板卡片与「配置导入」的用户卡片共用，重复任务每个实例一个标签 -->
  <div class="preset-tasks-preview">
    <div
      v-for="chip in chips"
      :key="chip.id"
      class="task-chip"
      :class="{ 'task-chip-invalid': chip.invalid }"
    >
      <span class="task-dot"></span>
      <span class="task-chip-name">{{ chip.label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** `invalid`：interface 已没有、或当前控制器 / 资源下不可用 */
  chips: ReadonlyArray<{ id: string; label: string; invalid?: boolean }>
}>()
</script>

<style scoped>
.preset-tasks-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--app-radius-panel);
  background: var(--ant-color-fill-quaternary);
}

.task-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 4px 12px 4px 8px;
  border-radius: var(--app-radius-pill);
  corner-shape: round;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-size: 13px;
}

.task-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  corner-shape: round;
  background: var(--ant-color-success);
  flex: 0 0 auto;
}

.task-chip-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 已失效：灰色、删除线、虚线边框、灰点（边框占的 1px 从内距里扣，标签不变大） */
.task-chip-invalid {
  padding: 4px 8px 4px 8px;
  border: 1px dashed var(--ant-color-border);
  background: transparent;
  color: var(--ant-color-text-tertiary);
}

.task-chip-invalid .task-chip-name {
  text-decoration: line-through;
}

.task-chip-invalid .task-dot {
  background: var(--ant-color-text-quaternary);
}
</style>
