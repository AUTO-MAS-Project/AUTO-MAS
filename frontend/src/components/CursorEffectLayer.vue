<script setup lang="ts">
import { computed, type Component } from 'vue'
import FluidCursor from '@/components/inspira/FluidCursor.vue'
import SleekLineCursor from '@/components/inspira/SleekLineCursor.vue'
import { useCursorEffectStore } from '@/stores/cursorEffect'
import { usePerformanceStore } from '@/stores/performance'

const cursorEffectStore = useCursorEffectStore()
const performanceStore = usePerformanceStore()

const effectComponent = computed<Component | null>(() => {
  if (cursorEffectStore.effect === 'sleek-line') {
    return SleekLineCursor
  }

  if (cursorEffectStore.effect === 'fluid') {
    return FluidCursor
  }

  return null
})
</script>

<template>
  <component :is="effectComponent" v-if="effectComponent && !performanceStore.isLowPower" />
</template>
