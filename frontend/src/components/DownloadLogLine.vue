<script setup lang="ts">
import { computed } from 'vue'
import type { WSTaskPrefetchData } from '@/services/websocket/types'
import { getDownloadParts } from '@/composables/useDownloadLogStyle'

const props = defineProps<{ data?: WSTaskPrefetchData | null }>()
const parts = computed(() => getDownloadParts(props.data))
</script>

<template>
  <div class="download-log-line">
    <template v-for="(part, index) in parts" :key="part.field">
      <span v-if="index"> · </span>
      <span :class="`download-log-${part.field}`">{{ part.text }}</span>
    </template>
  </div>
</template>

<style scoped>
.download-log-line {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
