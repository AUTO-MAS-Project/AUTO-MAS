<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>{{ scriptName || 'MAA' }}</a-breadcrumb-item>
      </a-breadcrumb>
      <h1>{{ isEdit ? '编辑 MAA 用户' : '添加 MAA 用户' }}</h1>
      <p>账号、关卡、任务与通知配置会在操作后即时保存</p>
    </div>

    <a-space size="small" wrap>
      <a-button
        v-if="userMode !== '简洁' && !showMaaConfigMask"
        type="primary"
        ghost
        :loading="maaConfigLoading"
        @click="$emit('handleMAAConfig')"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        MAA配置
      </a-button>
      <a-tag v-if="userMode !== '简洁' && showMaaConfigMask" color="processing"> 正在配置 </a-tag>
      <a-button class="cancel-button" @click="$emit('handleCancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeftOutlined, SettingOutlined } from '@ant-design/icons-vue'

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userMode: string
  maaConfigLoading: boolean
  showMaaConfigMask: boolean
  loading: boolean
}>()

defineEmits<{
  handleMAAConfig: []
  handleCancel: []
}>()
</script>

<style scoped>
.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: var(--v6-space-4);
  max-width: 1320px;
  margin: 0 auto var(--v6-space-5);
  padding: 0 var(--v6-space-1);
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0 0 var(--v6-space-2);
  font-size: var(--v6-font-size-sm);
}

.header-nav h1 {
  margin: 0;
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-3xl);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-tight);
  letter-spacing: -0.02em;
}

.header-nav p {
  margin: var(--v6-space-1) 0 0;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-base);
}

.cancel-button {
  border: 1px solid var(--v6-color-border);
  background: var(--v6-vibrancy-content);
  color: var(--v6-color-text);
  backdrop-filter: blur(18px) saturate(1.15);
}

.cancel-button:hover {
  border-color: var(--v6-color-info);
  color: var(--v6-color-info);
}

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: var(--v6-space-4);
    align-items: stretch;
  }
}
</style>
