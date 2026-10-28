<template>
  <a
    class="doc-link"
    :href="localizedUrl"
    target="_blank"
    rel="noreferrer"
    :aria-label="t('core.common.viewPageDocs')"
    @click.prevent="openHelpLink(localizedUrl, 'docs', entrySource)"
  >
    <BookOutlined />
    {{ t('core.common.viewPageDocs') }}
    <ExportOutlined />
  </a>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { BookOutlined, ExportOutlined } from '@ant-design/icons-vue'
import { openHelpLink, localizeDocUrl } from '@/utils/openExternal'
import type { AnalyticsEventProps } from '@/types/analytics'
import { useLocale } from '@/composables/useLocale'
import { useRoute } from 'vue-router'

const props = defineProps<{
  url: string
  entrySource?: AnalyticsEventProps['help_link_requested']['entry_source']
}>()
const route = useRoute()
const entrySource = computed(
  () =>
    props.entrySource ??
    (route.name === 'Home'
      ? 'home'
      : route.name === 'Settings'
        ? 'settings'
        : route.name === 'Initialization'
          ? 'initialization'
          : /ScriptEdit|UserEdit|SetupWizard/.test(String(route.name))
            ? 'script'
            : 'other')
)
const { t } = useI18n()
const { locale } = useLocale()
/** 按界面语言打开对应语言的文档，避免英文用户落在中文文档页。 */
const localizedUrl = computed(() => localizeDocUrl(props.url, locale.value))
</script>

<style scoped>
.doc-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-primary);
  white-space: nowrap;
}
</style>
