<template>
  <div
    v-if="activeAppearance?.backgroundUrl || customBackgroundUrl"
    class="appearance-decoration"
    aria-hidden="true"
  >
    <div class="appearance-background" />
  </div>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { activeAppearance, customBackgroundUrl } = useTheme()
</script>

<style scoped>
.appearance-decoration {
  display: contents;
  pointer-events: none;
  overflow: hidden;
}

.appearance-background {
  position: fixed;
  z-index: 0;
  inset: 0;
  pointer-events: none;
  background-image: var(--app-appearance-background-image);
  background-repeat: no-repeat;
  background-position: var(--app-appearance-background-position);
  background-size: var(--app-appearance-background-size);
  opacity: var(--app-appearance-background-opacity);
}

/* 标题栏是窗口控制区，自定义背景只填充其下方内容区。 */
body:has(.title-bar) .appearance-background {
  inset: 32px 0 0;
}
</style>
