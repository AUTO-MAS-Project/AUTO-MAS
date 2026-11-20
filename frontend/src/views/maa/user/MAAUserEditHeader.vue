<template>
  <UserEditHeader
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    :user-id="userId"
    :cancel-loading="cancelLoading"
    script-edit-segment="maa"
    @cancel="emit('cancel')"
  />
</template>

<script setup lang="ts">
import UserEditHeader from '@/components/UserEditHeader.vue'

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userId?: string
  cancelLoading: boolean
}>()
const emit = defineEmits<{ cancel: [] }>()
</script>
