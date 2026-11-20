<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { InstallTask } from '../usePluginInstallation'
import { installPhaseLabelKey, type InstallPhase } from '../pluginCenterModel'

/**
 * 卡片的状态位：排队、安装阶段进度、需要重启后端的提示、失败。
 * 没有任务或已完成时保留高度、不显示内容（完成后由卡片的「已安装」标识说明结果）。
 */
const props = defineProps<{ task: InstallTask | null }>()
const { t } = useI18n()

/** 进度条只表示走到第几个阶段，后端不报告字节进度。 */
const STAGE_PERCENT: Partial<Record<InstallPhase, number>> = {
  running: 33,
  restarting: 67,
  recovering: 67,
}

const phase = computed(() => props.task?.phase ?? null)
const label = computed(() =>
  props.task ? t(installPhaseLabelKey(props.task.phase, props.task.upgrade)) : ''
)
const percent = computed(() => (phase.value ? STAGE_PERCENT[phase.value] : undefined))
</script>

<template>
  <div class="market-install-status">
    <div v-if="percent !== undefined" role="status" class="market-install-progress">
      <a-progress
        :percent="percent"
        :show-info="false"
        size="small"
        :status="phase === 'recovering' ? 'exception' : 'active'"
      />
      <div class="market-install-text" :title="label">{{ label }}</div>
    </div>
    <div v-else-if="phase === 'waiting'" role="status" class="market-install-notice" :title="label">
      {{ label }}
    </div>
    <div v-else-if="phase === 'queued'" role="status" class="market-install-text">
      {{ label }}
    </div>
    <div v-else-if="phase === 'failed'" class="market-install-text market-install-text--error">
      {{ label }}
    </div>
  </div>
</template>

<style scoped>
.market-install-status {
  display: flex;
  min-height: 40px;
  flex-direction: column;
  justify-content: center;
}

.market-install-progress :deep(.ant-progress) {
  margin: 0;
  line-height: 1;
}

.market-install-text {
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-install-text--error {
  color: var(--ant-color-error);
}

.market-install-notice {
  display: -webkit-box;
  overflow: hidden;
  padding: 0 8px;
  border-radius: 6px;
  color: var(--ant-color-warning-text);
  background: var(--ant-color-warning-bg);
  font-size: 12px;
  line-height: 20px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
</style>
