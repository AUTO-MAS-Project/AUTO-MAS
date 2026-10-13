<script setup lang="ts">
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PageSurface from '@/components/PageSurface.vue'

const route = useRoute()
</script>

<template>
  <main class="migration-pending-page">
    <PageHeader :title="String(route.meta.title || '页面')" />
    <PageSurface class="migration-pending-surface">
      <a-empty description="该页面正在迁移到新配置框架" />
    </PageSurface>
  </main>
</template>

<style scoped>
.migration-pending-page {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.migration-pending-surface {
  display: flex;
  min-height: 0;
  flex: 1;
  align-items: center;
  justify-content: center;
}
</style>
