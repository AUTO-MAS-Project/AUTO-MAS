<template>
  <UserEditHeader
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    script-edit-segment="maaend"
    :user-id="userId"
    button-size="middle"
    actions-size="middle"
    @cancel="emit('cancel')"
  >
  </UserEditHeader>
</template>

<script setup lang="ts">
import UserEditHeader from '@/components/UserEditHeader.vue'

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userId?: string
}>()

const emit = defineEmits<{
  cancel: []
}>()
</script>
