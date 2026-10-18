<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/maaend`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? '编辑用户' : '添加用户' }}
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button v-if="props.userId" size="large" :loading="folderLoading" @click="handleOpenFolder">
        <template #icon>
          <FolderOpenOutlined />
        </template>
        {{ t('comp.openConfigFolder') }}
      </a-button>
      <a-button size="large" class="cancel-button" @click="$emit('handleCancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ArrowLeftOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import { useUserApi } from '@/composables/useUserApi'

const { t } = useI18n()

const props = defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userId?: string
}>()

defineEmits<{
  handleCancel: []
}>()

const { loading: folderLoading, openUserConfigFolder } = useUserApi()

const handleOpenFolder = async () => {
  if (!props.userId) return
  await openUserConfigFolder(props.scriptId, props.userId)
}
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

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }
}
</style>
