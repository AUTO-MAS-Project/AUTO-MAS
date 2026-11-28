<template>
  <UserEditHeader
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    :user-id="userId"
    :cancel-loading="cancelLoading"
    script-edit-segment="maa"
    @cancel="emit('cancel')"
  >
    <template v-if="isEdit && userName" #account-identity>
      <span class="account-identity" :title="userName">
        <img :src="accountIcon" alt="" />
        <span>{{ userName }}</span>
      </span>
    </template>
  </UserEditHeader>
</template>

<script setup lang="ts">
import accountIcon from '@maa/MAA.png'
import UserEditHeader from '@/components/UserEditHeader.vue'

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userName: string
  userId?: string
  cancelLoading: boolean
}>()
const emit = defineEmits<{ cancel: [] }>()
</script>

<style scoped>
.account-identity {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-weight: 600;
}

.account-identity img {
  width: 24px;
  height: 24px;
  object-fit: contain;
  flex: none;
}

.account-identity span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
