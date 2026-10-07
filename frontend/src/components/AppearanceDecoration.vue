<template>
  <div v-if="activeAppearance" class="appearance-decoration" aria-hidden="true">
    <div v-if="activeAppearance.backgroundUrl" class="appearance-background" />
    <img
      v-if="showMascot && activeAppearance.mascotUrl"
      class="appearance-mascot"
      :src="activeAppearance.mascotUrl"
      :style="mascotStyle"
      alt=""
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from '@/composables/useTheme'

withDefaults(defineProps<{ showMascot?: boolean }>(), { showMascot: true })

const { activeAppearance } = useTheme()
const mascotStyle = computed(() => {
  const position = activeAppearance.value?.mascot?.position ?? 'bottom-right'
  const positions = {
    'top-left': { top: '40px', left: '16px' },
    'top-right': { top: '40px', right: '16px' },
    'bottom-left': { bottom: '16px', left: '16px' },
    'bottom-right': { bottom: '16px', right: '16px' },
  } as const
  return positions[position]
})
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

.appearance-mascot {
  position: fixed;
  z-index: 10;
  pointer-events: none;
  width: var(--app-appearance-mascot-width);
  max-width: 35vw;
  height: auto;
  max-height: 30vh;
  object-fit: contain;
  opacity: var(--app-appearance-mascot-opacity);
}

@media (max-width: 800px) {
  .appearance-mascot {
    display: none;
  }
}
</style>
