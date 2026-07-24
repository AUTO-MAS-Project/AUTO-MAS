<template>
  <span
    class="v6-focus-ring"
    :class="{ 'v6-focus-ring--inline': inline }"
    tabindex="-1"
    aria-hidden="true"
  >
    <slot />
  </span>
</template>

<script setup lang="ts">
/**
 * FocusRing：仅作为视觉焦点环封装的可选容器组件。
 * 大多数情况下应直接使用 .v6-focus-ring CSS 类（见 v6-tokens.css 的 --v6-focus-ring）。
 * 此组件用于需要包裹一组交互元素并统一显式焦点样式的场景。
 */
interface Props {
  inline?: boolean
}

withDefaults(defineProps<Props>(), {
  inline: false,
})
</script>

<style scoped>
.v6-focus-ring {
  display: block;
  outline: none;
  border-radius: var(--v6-radius-control);
}

.v6-focus-ring--inline {
  display: inline-block;
}

.v6-focus-ring:focus,
.v6-focus-ring:focus-within {
  outline: none;
  box-shadow: var(--v6-focus-ring);
}

/* 低性能模式 / reduced-motion 下保持焦点环可见但去除过渡 */
:root[data-perf-mode='low'] .v6-focus-ring:focus,
:root[data-perf-mode='low'] .v6-focus-ring:focus-within {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .v6-focus-ring:focus,
  .v6-focus-ring:focus-within {
    transition: none;
  }
}
</style>
