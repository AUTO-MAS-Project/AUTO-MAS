<template>
  <div class="launch-status" aria-live="polite">
    <p class="launch-title">{{ title }}</p>

    <div
      class="launch-rail"
      :class="{ determinate: hasProgress }"
      role="progressbar"
      :aria-valuenow="hasProgress ? clampedProgress : undefined"
      :aria-valuemin="hasProgress ? 0 : undefined"
      :aria-valuemax="hasProgress ? 100 : undefined"
      :aria-label="title"
    >
      <span :style="hasProgress ? { width: `${clampedProgress}%` } : undefined"></span>
    </div>

    <ul v-if="details" class="launch-details" aria-live="off">
      <li v-for="(line, index) in details" :key="index" class="launch-detail">{{ line }}</li>
    </ul>

    <ol v-if="steps.length > 0" class="launch-track">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="launch-node"
        :class="step.state"
        :aria-current="step.state === 'current' ? 'step' : undefined"
      >
        <span class="launch-node-body">
          <CheckOutlined v-if="step.state === 'done'" class="launch-tick" aria-hidden="true" />
          <i v-else class="launch-dot" aria-hidden="true"></i>
          {{ step.label }}
        </span>
        <span v-if="index < steps.length - 1" class="launch-link" aria-hidden="true"></span>
      </li>
    </ol>

    <p v-if="hint" class="launch-hint">{{ hint }}</p>

    <button v-if="actionLabel" type="button" class="launch-action" @click="emit('action')">
      {{ actionLabel }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CheckOutlined } from '@ant-design/icons-vue'
import type { LaunchStep } from '@/types/launch'

defineOptions({ name: 'LaunchStatus' })

interface Props {
  /** 主状态句，例如「正在安装依赖」。 */
  title: string
  /** 次要说明，没有就不占位。 */
  hint?: string
  /** 0–100 的真实进度；后端给不出时留空走不定态，不显示百分比。 */
  progress?: number
  /**
   * 进度条下面的细节行，例如正在下载的文件名与速度。
   *
   * 传了数组（哪怕为空）就把两行的位置固定留出来：细节随事件一条条出现又消失，
   * 不留位的话整块居中内容会跟着上下跳。不传就完全不占位。
   */
  details?: string[]
  steps?: LaunchStep[]
  /** 可点的出口文案，例如「查看日志」。 */
  actionLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  hint: '',
  progress: undefined,
  details: undefined,
  steps: () => [],
  actionLabel: '',
})

const emit = defineEmits<{ action: [] }>()

const hasProgress = computed(() => props.progress !== undefined)
const clampedProgress = computed(() => Math.min(100, Math.max(0, Math.round(props.progress ?? 0))))
</script>

<style scoped>
.launch-status {
  inline-size: min(100%, 360px);
}

.launch-title {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 20px;
  font-weight: 500;
  line-height: 1.5;
}

.launch-rail {
  height: 2px;
  margin-top: 18px;
  border-radius: 2px;
  background: var(--ant-color-fill-secondary);
  overflow: hidden;
}

.launch-rail span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--ant-color-primary);
}

.launch-rail:not(.determinate) span {
  width: 36%;
  animation: launch-sweep 1.6s cubic-bezier(0.6, 0, 0.35, 1) infinite;
}

.launch-rail.determinate span {
  transition: width 0.4s ease;
}

.launch-details {
  /* 两行的位置固定留出来，细节出现和消失时下面的步骤条不会上下跳。 */
  min-height: calc(2 * 12px * 1.7);
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.7;
}

.launch-detail {
  /* 文件名没有空格可断，让它在任意位置折行而不是撑宽整块。 */
  overflow-wrap: anywhere;
}

@keyframes launch-sweep {
  from {
    transform: translateX(-105%);
  }

  to {
    transform: translateX(385%);
  }
}

.launch-track {
  display: flex;
  align-items: center;
  margin: 20px 0 0;
  padding: 0;
  list-style: none;
}

.launch-node {
  display: contents;
}

.launch-node-body {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--ant-color-text-quaternary);
  font-size: 12px;
  white-space: nowrap;
}

.launch-node.done .launch-node-body {
  color: var(--ant-color-text-tertiary);
}

.launch-node.current .launch-node-body {
  color: var(--ant-color-text);
  font-weight: 500;
}

.launch-dot {
  width: 6px;
  height: 6px;
  border: 1px solid currentcolor;
  border-radius: 50%;
}

.launch-node.current .launch-dot {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary);
}

.launch-tick {
  color: var(--ant-color-success);
  font-size: 11px;
}

.launch-link {
  flex: 1;
  height: 1px;
  margin: 0 9px;
  background: var(--ant-color-fill-secondary);
}

.launch-hint {
  margin: 16px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12.5px;
  line-height: 1.7;
}

.launch-action {
  margin-top: 14px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ant-color-primary);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
}

.launch-action:hover {
  color: var(--ant-color-primary-hover);
}

@media (prefers-reduced-motion: reduce) {
  .launch-rail:not(.determinate) span {
    width: 100%;
    animation: none;
  }

  .launch-rail.determinate span {
    transition: none;
  }
}
</style>
