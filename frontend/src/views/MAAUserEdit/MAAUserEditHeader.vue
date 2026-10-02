<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/maa`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? t('comp.editUser') : t('comp.addUser2') }}
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
      <a-button
        v-if="userMode === '用户' && !showMaaConfigMask"
        type="primary"
        ghost
        size="large"
        :loading="maaConfigLoading"
        :disabled="configLocked"
        @click="$emit('handleMAAConfig')"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ t('edit.maaConfiguration') }}
      </a-button>
      <a-button
        v-if="userMode === '用户' && showMaaConfigMask"
        type="default"
        size="large"
        disabled
        style="color: #52c41a; border-color: #52c41a"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ t('edit.configuring') }}
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
import { ArrowLeftOutlined, FolderOpenOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { useUserApi } from '@/composables/useUserApi'

const { t } = useI18n()

const props = defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userMode: string
  maaConfigLoading: boolean
  showMaaConfigMask: boolean
  loading: boolean
  configLocked: boolean
  userId?: string
}>()

defineEmits<{
  handleMAAConfig: []
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
