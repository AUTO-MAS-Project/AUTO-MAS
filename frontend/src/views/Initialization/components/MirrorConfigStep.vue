<template>
  <div class="step-panel">
    <h3>{{ t('init.mirror.title') }}</h3>
    <div class="install-section">
      <div class="mirror-status">
        <a-spin v-if="loading" size="large" :tip="t('init.mirror.loading')" />
        <a-result
          v-else-if="success"
          status="success"
          :title="t('init.mirror.loadedTitle')"
          :sub-title="t('init.mirror.loadedSubtitle', { count: mirrorCount })"
        />
        <a-result
          v-else
          status="warning"
          :title="t('init.mirror.fallbackTitle')"
          :sub-title="t('init.mirror.fallbackSubtitle')"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  loading: boolean
  success: boolean
  mirrorCount: number
}>()

const { t } = useI18n()
</script>

<style scoped>
.step-panel {
  padding: 20px;
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.step-panel h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
}

.install-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.install-section p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.mirror-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>
