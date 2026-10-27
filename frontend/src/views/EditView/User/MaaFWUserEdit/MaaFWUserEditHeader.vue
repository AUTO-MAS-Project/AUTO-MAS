<template>
  <UserEditHeader
    class="maafw-user-edit-header"
    :script-id="scriptId"
    :script-name="scriptName || 'MFW'"
    :script-route="scriptRoute"
    :is-edit="isEdit"
    :user-id="userId"
    :cancel-loading="leaving"
    actions-size="small"
    @cancel="emit('cancel')"
  >
    <template #breadcrumb-extra>
      <Transition name="save-chip-fade">
        <span
          v-if="saveStatus !== 'idle'"
          :class="['save-status-chip', `save-status-chip-${saveStatus}`]"
        >
          <LoadingOutlined v-if="saveStatus === 'saving'" spin />
          <CheckCircleOutlined v-else-if="saveStatus === 'saved'" />
          <a-tooltip v-else :title="saveErrorMessage || t('edit.saveFailedRetry')">
            <CloseCircleOutlined />
          </a-tooltip>
          <span>{{
            saveStatus === 'saving'
              ? t('edit.savingNow')
              : saveStatus === 'saved'
                ? t('edit.autoSaved')
                : t('edit.saveFailedShort')
          }}</span>
        </span>
      </Transition>
    </template>
  </UserEditHeader>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import UserEditHeader from '@/components/UserEditHeader.vue'
import type {
  MaaFWUserHeaderSectionEmits,
  MaaFWUserHeaderSectionProps,
} from '../../MaaFWFlavor/sectionContracts'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
defineProps<MaaFWUserHeaderSectionProps>()

const emit = defineEmits<MaaFWUserHeaderSectionEmits>()
</script>

<style scoped>
.maafw-user-edit-header {
  max-width: 1400px;
  margin: 0 auto 24px;
  padding: 0;
  gap: 16px;
}

.maafw-user-edit-header :deep(.breadcrumb-link) {
  display: inline-flex;
  align-items: center;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
  white-space: nowrap;
  /* 脚本名可能很长，中间那级要能收缩，否则会把「返回」按钮挤出可视区 */
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.maafw-user-edit-header :deep(.breadcrumb-link:hover) {
  color: var(--ant-color-primary);
}

.maafw-user-edit-header :deep(.breadcrumb-current) {
  display: inline-flex;
  align-items: center;
  color: var(--ant-color-text);
  font-weight: 600;
  white-space: nowrap;
}

.save-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  white-space: nowrap;
}

.save-status-chip-saving {
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-tertiary);
}

.save-status-chip-saved {
  color: var(--ant-color-success);
  background: var(--ant-color-success-bg);
}

.save-status-chip-error {
  color: var(--ant-color-error);
  background: var(--ant-color-error-bg);
}

.save-chip-fade-enter-active,
.save-chip-fade-leave-active {
  transition: opacity 0.2s ease;
}

.save-chip-fade-enter-from,
.save-chip-fade-leave-to {
  opacity: 0;
}
</style>
