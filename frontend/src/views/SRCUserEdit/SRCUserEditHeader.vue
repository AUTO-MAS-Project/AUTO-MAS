<template>
  <UserEditHeader
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    script-edit-segment="src"
    :current-label="isEdit ? t('comp.editUser') : t('comp.addUser')"
    :user-id="userId"
    :config-label="userMode === 'independent' ? t('edit.srcConfiguration') : undefined"
    :config-loading="srcConfigLoading"
    :config-active="showSrcConfigMask"
    :config-disabled="configLocked"
    @config="emit('config')"
    @cancel="emit('cancel')"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UserEditHeader from '@/components/UserEditHeader.vue'

const { t } = useI18n()

defineProps<{
  scriptId: string
  scriptName: string
  isEdit: boolean
  userMode: string
  srcConfigLoading: boolean
  showSrcConfigMask: boolean
  configLocked: boolean
  userId?: string
}>()

const emit = defineEmits<{
  config: []
  cancel: []
}>()
</script>
