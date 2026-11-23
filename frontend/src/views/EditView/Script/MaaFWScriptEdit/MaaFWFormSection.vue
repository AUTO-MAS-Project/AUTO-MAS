<template>
  <SectionCard
    variant="plain"
    :title="title"
    :density="compact ? 'compact' : 'default'"
    class="maafw-form-section"
    :class="{ 'maafw-form-section--compact': compact }"
  >
    <slot />
  </SectionCard>
</template>

<script setup lang="ts">
import { SectionCard } from '@/components/ui'

withDefaults(
  defineProps<{
    title: string
    compact?: boolean
  }>(),
  {
    compact: false,
  }
)
</script>

<style scoped>
.maafw-form-section {
  margin-bottom: 32px;
}

.maafw-form-section--compact {
  margin-bottom: 20px;
}
</style>
