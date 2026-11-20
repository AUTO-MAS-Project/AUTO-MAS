<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { PluginStatus } from '../pluginCenterModel'

/** 插件主状态；不认识的状态显示原值、用中性颜色。 */
defineProps<{ status: PluginStatus }>()
const { t } = useI18n()
</script>

<template>
  <a-tag
    class="plugin-status-tag"
    :color="status.tone"
    :bordered="false"
    :role="status.tone === 'processing' ? 'status' : undefined"
    >{{ status.labelKey ? t(status.labelKey) : status.raw }}</a-tag
  >
</template>

<style scoped>
.plugin-status-tag {
  margin-inline-end: 0;
}
</style>
