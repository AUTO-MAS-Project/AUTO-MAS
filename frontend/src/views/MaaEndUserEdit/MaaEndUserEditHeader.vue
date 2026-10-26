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
          {{ t(isEdit ? 'edit.maaEndEditAccount' : 'edit.maaEndAddAccount') }}
        </a-breadcrumb-item>
      </a-breadcrumb>
      <div class="account-heading">
        <img :src="maaEndIcon" alt="" class="account-icon" />
        <div class="account-title">
          <h1>{{ userName || t(isEdit ? 'edit.maaEndEditAccount' : 'edit.maaEndAddAccount') }}</h1>
          <span
            ><LoadingOutlined v-if="saving" />
            {{ t(saving ? 'edit.maaEndSaving' : 'edit.maaEndAutoSaveHint') }}</span
          >
        </div>
      </div>
    </div>

    <a-space size="middle">
      <a-button v-if="props.userId" :loading="folderLoading" @click="handleOpenFolder">
        <template #icon>
          <FolderOpenOutlined />
        </template>
        {{ t('comp.openConfigFolder') }}
      </a-button>
      <a-button @click="$emit('handleCancel')">
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
import { ArrowLeftOutlined, FolderOpenOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import { useUserApi } from '@/composables/useUserApi'
import maaEndIcon from '@/assets/MaaEnd.png'

const { t } = useI18n()

const props = defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userId?: string
  userName: string
  saving: boolean
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
  margin-bottom: 24px;
  padding-bottom: 24px;
  gap: 24px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.header-nav {
  flex: 1;
  min-width: 0;
}

.breadcrumb {
  margin: 0;
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
.breadcrumb {
  font-size: 12px;
}

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }
}
</style>
