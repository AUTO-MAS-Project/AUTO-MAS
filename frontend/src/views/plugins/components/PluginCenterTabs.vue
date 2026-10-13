<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const activeKey = route.path.startsWith('/plugins/market') ? 'market' : 'installed'

const onChange = (key: string) => {
  void router.push(key === 'market' ? { name: 'PluginMarket' } : { name: 'Plugins' })
}
</script>

<template>
  <a-tabs class="plugin-center-tabs" type="card" :active-key="activeKey" @change="onChange">
    <a-tab-pane key="installed" :tab="$t('plugins.installedTab')" />
    <a-tab-pane key="market" :tab="$t('plugins.marketTab')" />
  </a-tabs>
</template>

<style scoped>
.plugin-center-tabs { margin-bottom: 0; }
.plugin-center-tabs :deep(.ant-tabs-nav) { margin-bottom: 24px; }
.plugin-center-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) { background: transparent; border: 1px solid var(--ant-color-border); border-radius: 8px 8px 0 0; margin-right: 8px; }
.plugin-center-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) { background: var(--ant-color-bg-container); border-bottom-color: var(--ant-color-bg-container); }
</style>
