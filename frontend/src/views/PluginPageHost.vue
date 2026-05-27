<template>
  <div class="plugin-page-host">
    <iframe
      v-if="frameSrc"
      class="plugin-page-frame"
      :src="frameSrc"
      :title="page.title"
      sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads allow-same-origin"
    />
    <a-result
      v-else
      status="warning"
      title="插件页面缺少入口"
      sub-title="该页面声明未提供可加载的 url。"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { OpenAPI } from '@/api'
import type { PageDeclaration } from '../router/pageDeclarations'

const props = defineProps<{
  page: PageDeclaration
}>()

const backendBase = computed(() => (OpenAPI.BASE || 'http://localhost:36163').replace(/\/+$/, ''))

const frameSrc = computed(() => {
  const rawUrl = props.page.url?.trim()
  if (!rawUrl) return ''
  if (/^https?:\/\//i.test(rawUrl) || rawUrl.startsWith('//')) {
    return rawUrl
  }
  if (rawUrl.startsWith('/')) {
    return `${backendBase.value}${rawUrl}`
  }
  return `${backendBase.value}/${rawUrl.replace(/^\/+/, '')}`
})
</script>

<style scoped>
.plugin-page-host {
  height: 100%;
  min-height: calc(100vh - 80px);
}

.plugin-page-frame {
  display: block;
  width: 100%;
  height: 100%;
  min-height: calc(100vh - 80px);
  border: 0;
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}
</style>
