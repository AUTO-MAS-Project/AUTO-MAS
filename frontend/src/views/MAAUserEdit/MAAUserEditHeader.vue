<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/maa`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? '编辑用户' : '添加用户' }}
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button
        v-if="userMode !== '简洁'"
        type="primary"
        ghost
        size="large"
        :loading="maaConfigLoading"
        @click="$emit('handleMAAConfig')"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        MAA配置
      </a-button>
      <a-button size="large" class="cancel-button" @click="$emit('handleCancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
      <a-button
        type="primary"
        size="large"
        :loading="loading"
        class="save-button"
        @click="$emit('handleSubmit')"
      >
        <template #icon>
          <SaveOutlined />
        </template>
        {{ isEdit ? '保存修改' : '创建用户' }}
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeftOutlined, SaveOutlined, SettingOutlined } from '@ant-design/icons-vue'

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userMode: string
  maaConfigLoading: boolean
  loading: boolean
}>()

defineEmits<{
  handleMAAConfig: []
  handleCancel: []
  handleSubmit: []
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

.save-button {
  background: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.save-button:hover {
  background: var(--ant-color-primary-hover);
  border-color: var(--ant-color-primary-hover);
}

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }
}
</style>
