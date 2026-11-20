<script setup lang="ts">
import { useI18n } from 'vue-i18n'

/** 「官方」「本地」标识；两者都不是时不渲染。本地优先于官方。 */
defineProps<{ official: boolean; local?: boolean }>()
const { t } = useI18n()
</script>

<template>
  <a-tag v-if="local" class="plugin-origin-tag" :bordered="false">{{
    t('core.plugins.badge.local')
  }}</a-tag>
  <a-tag v-else-if="official" class="plugin-origin-tag" color="processing" :bordered="false">{{
    t('core.plugins.badge.official')
  }}</a-tag>
</template>

<style scoped>
.plugin-origin-tag {
  margin-inline-end: 0;
}
</style>
