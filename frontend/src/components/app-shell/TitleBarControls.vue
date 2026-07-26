<script setup lang="ts">
import { computed } from 'vue'
import { BorderOutlined, CloseOutlined, MinusOutlined } from '@ant-design/icons-vue'

const props = defineProps<{
  isMaximized: boolean
  hideCloseButton?: boolean
}>()

const emit = defineEmits<{
  (e: 'minimize'): void
  (e: 'toggle-maximize'): void
  (e: 'close'): void
}>()

const maximizeLabel = computed(() => (props.isMaximized ? '还原' : '最大化'))
</script>

<template>
  <div class="title-bar-controls" role="group" aria-label="窗口控制">
    <button
      v-if="!hideCloseButton"
      type="button"
      class="control-button close-button"
      title="关闭"
      aria-label="关闭"
      @click="emit('close')"
    >
      <CloseOutlined aria-hidden="true" />
    </button>
    <button
      type="button"
      class="control-button minimize-button"
      title="最小化"
      aria-label="最小化"
      @click="emit('minimize')"
    >
      <MinusOutlined aria-hidden="true" />
    </button>
    <button
      type="button"
      class="control-button maximize-button"
      :title="maximizeLabel"
      :aria-label="maximizeLabel"
      @click="emit('toggle-maximize')"
    >
      <BorderOutlined aria-hidden="true" />
    </button>
  </div>
</template>

<style scoped>
.title-bar-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 100%;
  padding-inline: 18px 12px;
  border-radius: 999px;
  backdrop-filter: blur(12px);
  user-select: none;
  -webkit-user-select: none;
  -webkit-app-region: no-drag;
}

.control-button {
  width: var(--v6-titlebar-button-size);
  height: var(--v6-titlebar-button-size);
  padding: 0;
  border: 0.5px solid rgb(0 0 0 / 18%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    transform var(--v6-motion-fast) var(--v6-ease-out),
    filter var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out);
  color: rgb(0 0 0 / 68%);
  font-size: 7px;
  line-height: 1;
  -webkit-app-region: no-drag;
}

.control-button :deep(.anticon) {
  opacity: 0;
  transition: opacity var(--v6-motion-fast) var(--v6-ease-out);
}

.title-bar-controls:hover .control-button :deep(.anticon),
.control-button:focus-visible :deep(.anticon) {
  opacity: 1;
}

.minimize-button {
  background: var(--v6-color-warning);
}

.maximize-button {
  background: var(--v6-color-success);
}

.close-button {
  background: var(--v6-color-error);
}

.control-button:hover {
  filter: brightness(0.92);
}

.control-button:active {
  filter: brightness(0.84);
  transform: scale(0.92);
}

.control-button:focus {
  outline: none;
  box-shadow: none;
}

.control-button:focus-visible {
  box-shadow: var(--v6-focus-ring-inset);
}

@media (prefers-reduced-motion: reduce) {
  .control-button {
    transition: none;
  }
}

:global(:root[data-perf-mode='low']) .control-button {
  transition: none;
}
</style>
