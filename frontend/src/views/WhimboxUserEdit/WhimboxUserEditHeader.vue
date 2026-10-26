<template>
  <UserEditHeader
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    script-edit-segment="whimbox"
    @cancel="emit('cancel')"
  >
    <template #extra-actions>
      <a-button size="large" class="cancel-button" @click="emit('restore')">
        <template #icon>
          <HistoryOutlined />
        </template>
        {{ t('edit.configRestoreTitle') }}
      </a-button>
    </template>
  </UserEditHeader>
</template>

<script setup lang="ts">
import { HistoryOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import UserEditHeader from '@/components/UserEditHeader.vue'

// 奇想盒备份实际位于 WhimboxBackups，通用配置文件夹入口会指向空目录，因此不展示
const { t } = useI18n()

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
}>()

const emit = defineEmits<{
  restore: []
  cancel: []
}>()
</script>
