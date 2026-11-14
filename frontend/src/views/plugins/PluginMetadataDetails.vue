<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PluginMeta_info } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'

const props = defineProps<{ info: PluginMeta_info }>()
const { t } = useI18n()
const links = computed(() =>
  /* 将发行链接转换为详情行，只允许远端元数据中的 HTTP/HTTPS 地址成为可点击链接。 */ [
    { label: 'docs', value: props.info.docs_url },
    { label: 'homepage', value: props.info.homepage },
    { label: 'repository', value: props.info.repository },
  ].map(item => {
    let href = ''
    try {
      const url = new URL(item.value || '')
      if (url.protocol === 'https:' || url.protocol === 'http:') href = url.href
    } catch {
      /* 保留非 URL 的原始声明供查看，不将其交给浏览器或系统协议处理器。 */
    }
    return { ...item, href }
  })
)
</script>

<template>
  <a-descriptions class="plugin-metadata" size="small" :column="3" bordered>
    <a-descriptions-item :label="t('core.plugins.attribute.name')">
      {{ info.display_name || info.plugin_name || '-' }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.attribute.pluginId')">
      {{ info.plugin_name || '-' }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.attribute.version')">
      {{ info.version || '-' }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.attribute.packageName')" :span="3">
      {{ info.package_name || '-' }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.attribute.author')">
      {{ info.author || '-' }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.attribute.license')">
      {{ info.license || '-' }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.tags')">
      {{ info.tags?.join(', ') || '-' }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.attribute.description')" :span="3">
      {{ info.description || t('core.plugins.noDescription') }}
    </a-descriptions-item>
    <a-descriptions-item :label="t('core.plugins.attribute.requiresDist')" :span="3">
      {{ info.requires_dist?.join(', ') || '-' }}
    </a-descriptions-item>
    <a-descriptions-item
      v-for="link in links"
      :key="link.label"
      :label="t(`core.plugins.attribute.${link.label}`)"
      :span="3"
    >
      <a
        v-if="link.href"
        :href="link.href"
        target="_blank"
        rel="noopener noreferrer"
        @click="handleExternalLink"
        >{{ link.value }}</a
      >
      <span v-else>{{ link.value || '-' }}</span>
    </a-descriptions-item>
  </a-descriptions>
</template>

<style scoped>
.plugin-metadata {
  overflow-wrap: anywhere;
}
</style>
