<template>
  <div class="user-edit-header">
    <div class="header-left">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/maafw`" class="breadcrumb-link">
            {{ scriptName || 'MaaFramework 项目' }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <span class="breadcrumb-current">{{ isEdit ? '编辑用户' : '添加用户' }}</span>
        </a-breadcrumb-item>
      </a-breadcrumb>
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
    </div>

    <a-space>
      <a-button size="large" @click="emit('cancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons-vue'

defineProps<{
  saveStatus: 'idle' | 'saving' | 'saved' | 'error'
  saveErrorMessage: string
  scriptId: string
  scriptName: string
  isEdit: boolean
}>()

const emit = defineEmits<{
  cancel: []
}>()
</script>

<style scoped>
.user-edit-header {
  max-width: 1400px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.header-left {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.breadcrumb-link {
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

.breadcrumb-link:hover {
  color: var(--ant-color-primary);
}

.breadcrumb-current {
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

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
