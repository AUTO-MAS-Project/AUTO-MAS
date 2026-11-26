<template>
  <SectionCard
    variant="card"
    :title="title"
    :density="compact ? 'compact' : 'default'"
    :icon="icon"
  >
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
