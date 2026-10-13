<template>
  <div ref="layer" class="float-layer"></div>
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { createFloatTextLayer, type FloatTextVariant } from './floatText'
import type { ScreenPoint } from './satelliteScene'

/** 卫星区域里冒的浮字（star!、彩蛋大字、台词气泡……），铺满卫星区域、不挡指针 */
const layer = ref<HTMLDivElement | null>(null)
const texts = createFloatTextLayer()

function spawn(point: ScreenPoint, text: string, variant: FloatTextVariant): void {
  if (layer.value) texts.spawn(layer.value, point, text, variant)
}

onUnmounted(() => texts.dispose())

defineExpose({ spawn, clear: texts.dispose })
</script>

<style scoped>
.float-layer {
  position: absolute;
  inset: 0;
  /* 压在场景画布和悬停标签上面 */
  z-index: 10;
  pointer-events: none;
}

/* 浮字是运行时创建的，不在模板里，scoped 的选择器要用 :deep 才管得到 */
.float-layer :deep(.star-burst) {
  position: absolute;
  transform: translate(-50%, -50%);
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--ant-color-warning);
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
  will-change: transform, opacity;
}

.float-layer :deep(.star-burst-hint) {
  font-size: 20px;
  color: var(--ant-color-primary);
}

.float-layer :deep(.star-burst-huge) {
  font-size: 44px;
  font-weight: 900;
  letter-spacing: 0.06em;
  color: var(--ant-color-warning);
  -webkit-text-stroke: 1.5px rgba(0, 0, 0, 0.35);
  text-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
}

.float-layer :deep(.star-burst-love) {
  font-size: 52px;
  font-weight: 900;
  color: #ff5c93;
  text-shadow:
    0 0 18px rgba(255, 92, 147, 0.7),
    0 4px 14px rgba(0, 0, 0, 0.3);
}

/* 角色台词：带尾巴的对话气泡 */
.float-layer :deep(.star-burst-speech) {
  max-width: 280px;
  padding: 6px 12px;
  border-radius: 12px;
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border-secondary);
  box-shadow: var(--ant-box-shadow-secondary);
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  white-space: normal;
  text-shadow: none;
}

.float-layer :deep(.star-burst-speech)::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -6px;
  width: 10px;
  height: 10px;
  background: inherit;
  border-right: 1px solid var(--ant-color-border-secondary);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  transform: translateX(-50%) rotate(45deg);
}

.float-layer :deep(.star-burst-rainbow) {
  background-image: linear-gradient(90deg, #ff5f6d, #ffc371, #47e5bc, #4facfe, #b06ab3, #ff5f6d);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
  text-shadow: none;
  animation: star-rainbow 1.2s linear infinite;
}

@keyframes star-rainbow {
  to {
    background-position: 200% center;
  }
}
</style>
