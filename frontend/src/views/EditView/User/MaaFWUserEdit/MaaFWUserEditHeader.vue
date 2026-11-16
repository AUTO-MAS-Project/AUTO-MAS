<template>
  <UserEditHeader
    :script-id="scriptId"
    :script-name="scriptName || 'MFW'"
    :script-route="scriptRoute"
    :is-edit="isEdit"
    :user-id="userId"
    :cancel-loading="leaving"
    @cancel="emit('cancel')"
  />
</template>

<script setup lang="ts">
import UserEditHeader from '@/components/UserEditHeader.vue'
import type {
  MaaFWUserHeaderSectionEmits,
  MaaFWUserHeaderSectionProps,
} from '../../MaaFWFlavor/sectionContracts'

defineProps<MaaFWUserHeaderSectionProps>()
const emit = defineEmits<MaaFWUserHeaderSectionEmits>()
</script>
