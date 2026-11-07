<template>
  <div class="empty-state">
    <NoData :image-style="{ height: '200px' }"
      ><template #description
        ><div class="empty-title">{{ t('core.plan.emptyTitle') }}</div>
        <div class="empty-description">{{ t('core.plan.emptyDesc') }}</div></template
      ></NoData
    >
  </div>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>
<style scoped>
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 500px;
  padding: 60px 20px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  margin: 20px 0;
}

.empty-title {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 8px;
}
.empty-description {
  color: var(--ant-color-text-secondary);
}
</style>
