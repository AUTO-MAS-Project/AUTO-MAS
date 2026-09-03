<template>
  <a class="doc-link" :href="localizedUrl" target="_blank" rel="noreferrer" :aria-label="t('common.viewPageDocs')" @click="handleExternalLink">
    <BookOutlined />
    {{ t('common.viewPageDocs') }}
    <ExportOutlined />
  </a>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { BookOutlined, ExportOutlined } from '@ant-design/icons-vue'
import { handleExternalLink, localizeDocUrl } from '@/utils/openExternal'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ url: string }>()
const { t } = useI18n()
const { locale } = useLocale()
/** 按界面语言打开对应语言的文档，避免英文用户落在中文文档页。 */
const localizedUrl = computed(() => localizeDocUrl(props.url, locale.value))
</script>

<style scoped>
.doc-link { display: inline-flex; align-items: center; gap: 4px; color: var(--ant-color-primary); white-space: nowrap; }
</style>
