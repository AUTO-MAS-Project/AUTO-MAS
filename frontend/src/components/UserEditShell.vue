<script setup lang="ts">
import ConfigEditShell from '@/components/ui/ConfigEditShell.vue'
import UserEditHeader from '@/components/UserEditHeader.vue'
import type { UserEditHeaderProps } from '@/types/userEditor'

const {
  surface = true,
  maxWidth = undefined,
  hideHeader,
  configVisible = true,
  ...header
} = defineProps<
  UserEditHeaderProps & { surface?: boolean; maxWidth?: number; hideHeader?: boolean }
>()
defineEmits<{ cancel: []; config: [] }>()
</script>

<template>
  <ConfigEditShell :surface="surface" :max-width="maxWidth" :fixed-header="!hideHeader">
    <template v-if="!hideHeader" #header>
      <UserEditHeader
        v-bind="header"
        :config-visible="configVisible"
        @cancel="$emit('cancel')"
        @config="$emit('config')"
      >
        <template #extra-actions><slot name="extra-actions" /></template>
      </UserEditHeader>
    </template>
    <template v-if="$slots.banner" #banner><slot name="banner" /></template>
    <slot />
    <template #overlay><slot name="overlay" /></template>
  </ConfigEditShell>
</template>
