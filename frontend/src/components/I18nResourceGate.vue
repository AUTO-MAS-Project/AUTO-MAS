<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBackendI18nStore } from '@/stores/backendI18n'
import { openLaunchLogWindow } from '@/utils/launch'
import BootstrapLanguageSelect from './BootstrapLanguageSelect.vue'

defineProps<{ standalone?: boolean }>()
defineEmits<{ retry: []; recover: []; close: [] }>()
const { t } = useI18n()
const resources = useBackendI18nStore()
</script>

<template>
  <div class="i18n-resource-gate" :class="{ standalone }" role="status">
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
      <a-button v-if="standalone" @click="$emit('close')">{{ t('bootstrap.comp.close') }}</a-button>
      <a-button v-else @click="$emit('recover')">{{ t('bootstrap.i18n.recover') }}</a-button>
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

/* 询问窗口只有 460×240；长错误由门禁自身滚动，操作按钮始终可达。 */
.i18n-resource-gate.standalone {
  height: 100%;
  min-height: 0;
  justify-content: flex-start;
  gap: 12px;
  padding: 16px;
  overflow-y: auto;
}

.i18n-resource-gate.standalone > * {
  flex-shrink: 0;
}
</style>
