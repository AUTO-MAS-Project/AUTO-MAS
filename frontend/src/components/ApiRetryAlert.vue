<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ error?: string | null; loading?: boolean }>()
defineEmits<{ retry: [] }>()
const { t } = useI18n()
</script>

<template>
  <a-alert v-if="error" type="error" show-icon :message="error">
    <template #action>
      <a-button size="small" :loading="loading" @click="$emit('retry')">
        {{ t('common.retry') }}
      </a-button>
    </template>
  </a-alert>
</template>
