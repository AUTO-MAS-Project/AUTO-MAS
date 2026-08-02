<template>
  <div class="plugin-page plugin-element-host">
    <a-spin v-if="loading" size="large" tip="正在加载插件页面" />
    <a-result
      v-else-if="errorMessage"
      status="warning"
      title="插件页面加载失败"
      :sub-title="errorMessage"
    />
    <component
      :is="resolvedTag"
      v-else-if="resolvedTag"
      :title="page.title"
      :data-page-id="page.id"
      :data-plugin-id="page.frontend_plugin || ''"
      class="plugin-element-host__root"
    />
    <a-result
      v-else
      status="warning"
      title="插件页面缺少入口"
      sub-title="页面声明未提供可用的 custom element。"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { PageDeclaration } from '@/router/pageDeclarations'
import { ensurePluginFrontendPage } from '@/plugin/pluginFrontendLoader'
import { setPluginPageContext } from '@/plugin/pluginPageContext'

const props = defineProps<{
  page: PageDeclaration
}>()

const loading = ref(true)
const errorMessage = ref('')

const resolvedTag = computed(() => props.page.element_tag || '')

function syncPageContext(): void {
  setPluginPageContext({
    pageId: props.page.id,
    path: props.page.path,
    title: props.page.title,
    renderer: props.page.renderer,
    source: props.page.source,
    pluginId: props.page.frontend_plugin,
    elementTag: props.page.element_tag,
  })
}

async function loadPage(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  syncPageContext()
  try {
    await ensurePluginFrontendPage(props.page)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.page,
  () => {
    void loadPage()
  },
  { deep: true }
)

onMounted(() => {
  void loadPage()
})

onBeforeUnmount(() => {
  setPluginPageContext(null)
})
</script>

<style scoped>
.plugin-element-host {
  display: flex;
  align-items: stretch;
  justify-content: center;
  min-height: 100%;
}

.plugin-element-host__root {
  display: block;
  width: 100%;
  min-height: 100%;
}
</style>
