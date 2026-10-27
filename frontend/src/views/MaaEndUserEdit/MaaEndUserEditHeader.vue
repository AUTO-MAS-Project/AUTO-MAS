<template>
  <UserEditHeader
    class="maaend-user-edit-header"
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    script-edit-segment="maaend"
    :current-label="t(isEdit ? 'edit.maaEndEditAccount' : 'edit.maaEndAddAccount')"
    :user-id="userId"
    button-size="middle"
    actions-size="middle"
    @cancel="emit('cancel')"
  >
    <template #below-breadcrumb>
      <div class="account-heading">
        <img :src="maaEndIcon" alt="" class="account-icon" />
        <div class="account-title">
          <h1>{{ userName || t(isEdit ? 'edit.maaEndEditAccount' : 'edit.maaEndAddAccount') }}</h1>
          <span>
            <LoadingOutlined v-if="saving" />
            {{ t(saving ? 'edit.maaEndSaving' : 'edit.maaEndAutoSaveHint') }}
          </span>
        </div>
      </div>
    </template>
  </UserEditHeader>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LoadingOutlined } from '@ant-design/icons-vue'
import UserEditHeader from '@/components/UserEditHeader.vue'
import maaEndIcon from '@/assets/MaaEnd.png'

const { t } = useI18n()

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userId?: string
  userName: string
  saving: boolean
}>()

const emit = defineEmits<{
  cancel: []
}>()
</script>

<style scoped>
.maaend-user-edit-header {
  margin-bottom: 24px;
  padding: 0 0 24px;
  gap: 24px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.maaend-user-edit-header :deep(.breadcrumb) {
  font-size: 12px;
}

.account-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}
.account-icon {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  object-fit: cover;
}
.account-title {
  min-width: 0;
}
.account-title h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
  overflow-wrap: anywhere;
}
.account-title span {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

@media (max-width: 768px) {
  .maaend-user-edit-header {
    gap: 16px;
  }
}
</style>
