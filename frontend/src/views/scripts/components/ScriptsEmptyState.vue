<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <NoData :image-style="{ height: '120px' }">
    <template #description>
      <h3 class="empty-title">{{ t('core.scripts.empty.title') }}</h3>
      <p class="empty-description">{{ t('core.scripts.empty.desc') }}</p>
    </template>
  </NoData>
</template>

<style scoped>
.empty-title {
  font-size: 18px;
  font-weight: 500;
  margin: 0;
  color: var(--ant-color-text);
}

.empty-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0;
}
</style>
