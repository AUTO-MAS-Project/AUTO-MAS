<script setup lang="ts">
import { useAppBackground } from '@/composables/useAppBackground.ts'

const {
  enabled: backgroundEnabled,
  source: backgroundSource,
  cssVars: backgroundCssVars,
} = useAppBackground()
</script>

<template>
  <div
    class="app-background-layer"
    aria-hidden="true"
    :class="{ 'has-background': backgroundEnabled }"
    :style="backgroundCssVars"
    :data-background-source="backgroundSource"
  >
    <div class="app-background-default" />
    <template v-if="backgroundEnabled">
      <div class="app-background-image" />
      <div class="app-background-overlay" />
    </template>
  </div>
</template>

<style scoped>
.app-background-layer {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: var(--v6-z-background);
  background: var(--v6-color-window);
}

.app-background-default {
  position: absolute;
  inset: 0;
  background: var(--v6-default-wallpaper);
}

.app-background-image {
  position: absolute;
  inset: -48px;
  background-image: var(--app-background-image);
  background-size: var(--app-background-size);
  background-position: var(--app-background-position);
  background-repeat: no-repeat;
  opacity: var(--app-background-opacity);
  filter: blur(var(--app-background-blur)) brightness(var(--app-background-brightness));
  transform: scale(1.03);
}

.app-background-overlay {
  position: absolute;
  inset: 0;
  background: var(--ant-color-bg-layout);
  opacity: var(--app-background-overlay-opacity);
}
</style>
