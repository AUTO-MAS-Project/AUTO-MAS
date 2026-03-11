<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/src`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? '编辑用户' : '添加用户' }}
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button v-if="userMode !== '简洁' && !showSrcConfigMask" type="primary" ghost size="large"
        :loading="srcConfigLoading" @click="$emit('handleSRCConfig')">
        <template #icon>
          <SettingOutlined />
        </template>
        SRC配置
      </a-button>
      <a-button v-if="userMode !== '简洁' && showSrcConfigMask" type="default" size="large" disabled
        style="color: #52c41a; border-color: #52c41a">
        <template #icon>
          <SettingOutlined />
        </template>
        正在配置
      </a-button>
      <a-button size="large" class="cancel-button" @click="$emit('handleCancel')">
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
  srcConfigLoading: boolean
  showSrcConfigMask: boolean
  loading: boolean
}>()

defineEmits<{
  handleSRCConfig: []
  handleCancel: []
}>()
</script>

<style scoped>
.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.cancel-button:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }
}
</style>
