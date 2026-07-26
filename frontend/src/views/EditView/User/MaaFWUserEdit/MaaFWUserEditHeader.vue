<template>
  <PageHeader
    class="user-edit-header"
    :title="`编辑 ${scriptName || 'MaaFramework'} 用户`"
    subtitle="配置任务队列、预设、账号记录与通知"
    compact
    transparent
    :bordered="false"
  >
    <template #title>
      <div class="header-title">
        <img
          :src="getScriptIcon(scriptType, scriptIconUrl)"
          :alt="scriptType || 'MaaFramework'"
          class="header-icon"
          @error="event => handleScriptIconError(event, scriptType)"
        />
        <span>{{ `编辑 ${scriptName || 'MaaFramework'} 用户` }}</span>
        <a-tag color="processing">MaaFW</a-tag>
      </div>
    </template>
    <template #default>
      <Transition name="save-chip-fade">
        <span
          v-if="saveStatus !== 'idle'"
          :class="['save-status-chip', `save-status-chip-${saveStatus}`]"
        >
          <LoadingOutlined v-if="saveStatus === 'saving'" spin />
          <CheckCircleOutlined v-else-if="saveStatus === 'saved'" />
          <a-tooltip v-else :title="saveErrorMessage || '保存失败，请重试'">
            <CloseCircleOutlined />
          </a-tooltip>
          <span>{{
            saveStatus === 'saving' ? '保存中…' : saveStatus === 'saved' ? '已自动保存' : '保存失败'
          }}</span>
        </span>
      </Transition>
    </template>
    <template #actions>
      <a-button size="large" @click="emit('cancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </template>
  </PageHeader>
</template>

<script setup lang="ts">
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons-vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import { getScriptIcon, handleScriptIconError } from '@/utils/scriptRegistry'

defineProps<{
  scriptName: string
  scriptType: string
  scriptIconUrl: string | null
  saveStatus: 'idle' | 'saving' | 'saved' | 'error'
  saveErrorMessage: string
}>()

const emit = defineEmits<{
  cancel: []
}>()
</script>

<style scoped>
.user-edit-header {
  max-width: 1400px;
  margin: 0 auto var(--v6-space-4);
}

.header-title {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--v6-space-2);
}

.header-title > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-icon {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  border-radius: var(--v6-radius-sm);
  object-fit: contain;
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

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
