<template>
  <div v-if="activeAppearance" class="appearance-decoration" aria-hidden="true">
    <div v-if="activeAppearance.backgroundUrl" class="appearance-background" />
  </div>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { activeAppearance } = useTheme()
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
</style>
