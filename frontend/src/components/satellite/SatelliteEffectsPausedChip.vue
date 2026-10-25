<script setup lang="ts">
import { PauseCircleOutlined } from '@ant-design/icons-vue'

const emit = defineEmits<{ resume: [] }>()
</script>

<template>
  <!-- 脚本运行期间主页动效自动暂停时的就地指示；点一下恢复到本轮任务结束为止 -->
  <button
    class="effects-paused-chip"
    type="button"
    @pointerdown.stop
    @pointermove.stop
    @pointerup.stop
    @pointercancel.stop
    @click.stop="emit('resume')"
  >
    <PauseCircleOutlined />
    <span>{{ $t('home.satelliteEffectsPaused') }}</span>
  </button>
</template>

<style scoped>
.effects-paused-chip {
  position: absolute;
  /* 右上角是开发者打榜按钮（SatelliteEggStage 的 .egg-launcher），挪到左上角避开 */
  top: 12px;
  left: 12px;
  z-index: 6;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--ant-color-border);
  border-radius: 999px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    color 0.2s ease;
}

.effects-paused-chip:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}
</style>
