<script setup lang="ts">
import { computed } from 'vue'

/**
 * 统一页面根骨架。
 *
 * scroll: 自然纵向滚动页；fill: 占满视口高度、由内部面板各自滚动（如历史记录、插件中心、日志）。
 */
const props = withDefaults(
  defineProps<{
    layout?: 'scroll' | 'fill'
    maxWidth?: number | string
  }>(),
  {
    layout: 'scroll',
    maxWidth: undefined,
  }
)

const containerStyle = computed(() => {
  if (props.maxWidth === undefined) return undefined
  const value = typeof props.maxWidth === 'number' ? `${props.maxWidth}px` : props.maxWidth
  return { maxWidth: value, marginInline: 'auto' }
})
</script>

<template>
  <main class="app-page" :class="`app-page--${layout}`" :style="containerStyle">
    <slot />
  </main>
</template>

<style scoped>
.app-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
}

.app-page--scroll {
  min-height: 100%;
}

.app-page--fill {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
