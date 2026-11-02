<template>
  <!-- 模拟器的截图 / 输入方式，只读两行 -->
  <a-descriptions :column="1" size="small" bordered class="control-strategy-summary">
    <a-descriptions-item v-for="item in items" :key="item.label" :label="item.label">
      {{ item.value }}
    </a-descriptions-item>
  </a-descriptions>
</template>

<script setup lang="ts">
import type { MaaFWScriptControlSectionProps } from '../../MaaFWFlavor/sectionContracts'

defineProps<{
  items: MaaFWScriptControlSectionProps['adbControlStrategyItems']
}>()
</script>

<style scoped>
/* 父级给的是 flex 列：表格撑满列高，再减去与 a-form-item 相同的底距（本项目全局把它定成 20px），
   上下边就与同一行的表单项对齐，两行均分高度 */
.control-strategy-summary {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  margin-bottom: 20px;
}

/* view 也做成 flex 列，表格作为 flex 项被拉到满高（height:100% 在这里解析不出来，差 3px） */
.control-strategy-summary :deep(.ant-descriptions-view) {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.control-strategy-summary :deep(.ant-descriptions-view table) {
  flex: 1;
}

.control-strategy-summary :deep(.ant-descriptions-item-label),
.control-strategy-summary :deep(.ant-descriptions-item-content) {
  padding: 4px 12px !important;
  font-size: 13px;
}

.control-strategy-summary :deep(.ant-descriptions-item-label) {
  width: 28%;
  color: var(--ant-color-text-secondary);
}
</style>
