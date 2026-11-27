<template>
  <SectionCard
    variant="card"
    :title="title"
    :density="compact ? 'compact' : 'default'"
    :icon="icon"
  >
    <template v-if="$slots.actions" #actions>
      <slot name="actions" />
    </template>
    <slot />
  </SectionCard>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { SectionCard } from '@/components/ui'

withDefaults(
  defineProps<{
    title: string
    icon: Component
    compact?: boolean
  }>(),
  {
    compact: false,
  }
)
</script>
