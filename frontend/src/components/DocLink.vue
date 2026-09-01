<template>
  <a class="doc-link" :href="url" target="_blank" rel="noreferrer" :aria-label="t('common.viewPageDocs')" @click="handleExternalLink">
    <BookOutlined />
    {{ t('common.viewPageDocs') }}
    <ExportOutlined />
  </a>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BookOutlined, ExportOutlined } from '@ant-design/icons-vue'
import { handleExternalLink } from '@/utils/openExternal'

defineProps<{ url: string }>()
const { t } = useI18n()
</script>

<style scoped>
.doc-link { display: inline-flex; align-items: center; gap: 4px; color: var(--ant-color-primary); white-space: nowrap; }
</style>
