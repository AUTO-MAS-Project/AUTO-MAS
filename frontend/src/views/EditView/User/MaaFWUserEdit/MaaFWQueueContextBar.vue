<template>
  <!-- 控制方式 / 游戏资源是脚本级设置，这里只显示；不兼容的实例只是不显示，快照原样保留 -->
  <div v-if="showQueueContext" class="queue-context">
    <span class="queue-context-text">{{ queueContextText }}</span>
    <a-tooltip
      v-if="hiddenQueueTaskNames.length > 0"
      placement="bottomLeft"
      :overlay-style="{ maxWidth: '360px' }"
    >
      <template #title>
        <div>{{ t('core.edit.maafwHiddenTaskTooltip') }}</div>
        <div v-for="name in hiddenQueueTaskNames" :key="name">{{ name }}</div>
      </template>
      <span class="queue-context-hidden">
        {{ t('core.edit.maafwHiddenTaskCount', { count: hiddenQueueTasks.length }) }}
      </span>
    </a-tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { isSupportedMaaFWControllerType } from '@/types/script'
import type { MaaFWInterfacePreviewData, MaaFWTaskInfo, MaaFWTaskSnapshot } from '@/types/script'
import { listMaaFWHiddenQueueTasks, summarizeMaaFWHiddenQueueTasks } from './maafwHiddenTasks'

/**
 * 队列框顶部一行：当前控制方式 / 游戏资源（脚本页设的），以及因不兼容而不显示的实例数。
 * 只读展示，不改快照。
 */

const props = defineProps<{
  previewData: MaaFWInterfacePreviewData | null
  taskSnapshot: Pick<MaaFWTaskSnapshot, 'taskOrder' | 'taskLabels'>
  taskByName: Map<string, MaaFWTaskInfo>
  effectiveControllerName: string
  effectiveResourceName: string
}>()

const { t } = useI18n()

const getDisplayName = (item: { name: string; label?: string | null }) => item.label || item.name

const hiddenQueueTasks = computed(() =>
  listMaaFWHiddenQueueTasks(
    props.taskSnapshot.taskOrder,
    props.taskByName,
    props.effectiveControllerName,
    props.effectiveResourceName,
    props.taskSnapshot.taskLabels
  )
)
const hiddenQueueTaskNames = computed(() => summarizeMaaFWHiddenQueueTasks(hiddenQueueTasks.value))
// 项目只有一种控制方式、一种资源时这行没有信息量，不显示（有隐藏的实例时照样显示）
const showQueueContext = computed(() => {
  const data = props.previewData
  if (!data) return false
  const controllerCount = data.controllers.filter(controller =>
    isSupportedMaaFWControllerType(controller.type)
  ).length
  return controllerCount > 1 || data.resources.length > 1 || hiddenQueueTasks.value.length > 0
})
const queueContextText = computed(() => {
  const data = props.previewData
  const controller = data?.controllers.find(item => item.name === props.effectiveControllerName)
  const resource = data?.resources.find(item => item.name === props.effectiveResourceName)
  return [
    controller &&
      t('core.edit.maafwQueueContextItem', {
        label: t('core.edit.controlMode'),
        value: getDisplayName(controller),
      }),
    resource &&
      t('core.edit.maafwQueueContextItem', {
        label: t('core.edit.gameResource'),
        value: getDisplayName(resource),
      }),
  ]
    .filter(Boolean)
    .join(' · ')
})
</script>

<style scoped>
/* 滚动时钉在队列框顶上 */
.queue-context {
  position: sticky;
  top: 0;
  z-index: 1;
  flex: none;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  padding: 6px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  /* 填充色是半透明的，垫一层容器底色，滚过去的行不透上来 */
  background:
    linear-gradient(var(--ant-color-fill-quaternary), var(--ant-color-fill-quaternary)),
    var(--ant-color-bg-container);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
}

.queue-context-text {
  min-width: 0;
  overflow-wrap: anywhere;
}

.queue-context-hidden {
  color: var(--ant-color-warning);
  cursor: help;
  white-space: nowrap;
}
</style>
