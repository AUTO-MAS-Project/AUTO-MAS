<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/whimbox`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? t('comp.editUser') : t('comp.addUser2') }}
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="emit('restore')">
        <template #icon>
          <HistoryOutlined />
        </template>
        {{ t('edit.configRestoreTitle') }}
      </a-button>
      <a-button size="large" class="cancel-button" @click="emit('back')">
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
import { ArrowLeftOutlined, HistoryOutlined } from '@ant-design/icons-vue'

// 刻意不带「打开配置文件夹」入口（其余专项头组件均有）：通用 /user/config-dir
// 指向 data/{scriptId}/{userId}，对奇想盒是空目录——它的双池备份实际位于
// data/{scriptId}/WhimboxBackups/（见 app/task/Whimbox/tools/restore_service.py），
// 通用端点指不到。要补入口需先扩端点，不在本 PR 范围。
const { t } = useI18n()

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
}>()

const emit = defineEmits<{
  restore: []
  back: []
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

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
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
