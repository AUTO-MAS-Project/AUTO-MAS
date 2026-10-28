<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBackendI18nStore } from '@/stores/backendI18n'
import { openLaunchLogWindow } from '@/utils/launch'
import BootstrapLanguageSelect from './BootstrapLanguageSelect.vue'

defineEmits<{ retry: []; recover: [] }>()
const { t } = useI18n()
const resources = useBackendI18nStore()
</script>

<template>
  <div class="i18n-resource-gate" role="status">
    <BootstrapLanguageSelect />
    <a-spin v-if="resources.loading" />
    <a-alert
      v-else-if="resources.error"
      type="error"
      show-icon
      :message="t('bootstrap.i18n.failed')"
      :description="resources.error"
    />
    <p v-else>{{ t('bootstrap.i18n.loading') }}</p>
    <a-space wrap>
      <a-button type="primary" :loading="resources.loading" @click="$emit('retry')">
        {{ t('bootstrap.i18n.retry') }}
      </a-button>
      <a-button @click="openLaunchLogWindow('语言资源加载')">
        {{ t('bootstrap.launch.viewLog') }}
      </a-button>
      <a-button @click="$emit('recover')">{{ t('bootstrap.i18n.recover') }}</a-button>
    </a-space>
  </div>
</template>

<style scoped>
.i18n-resource-gate {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  gap: 24px;
  padding: 32px;
  color: var(--ant-color-text);
}
</style>
