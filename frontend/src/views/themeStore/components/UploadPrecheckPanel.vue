<script setup lang="ts">
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { UploadPrecheckResult } from '../uploadPrecheck'

defineProps<{
  result: UploadPrecheckResult
}>()

const { t } = useI18n()
</script>

<template>
  <section class="precheck-panel">
    <div class="precheck-header">
      <span class="precheck-title">{{ t('core.themeStore.upload.precheck.title') }}</span>
      <a-tag v-if="result.hasBlockingError" color="error" class="precheck-badge">
        {{ t('core.themeStore.upload.precheck.blockedBadge') }}
      </a-tag>
      <a-tag v-else-if="result.warningCount > 0" color="warning" class="precheck-badge">
        {{ t('core.themeStore.upload.precheck.warningBadge', { count: result.warningCount }) }}
      </a-tag>
      <a-tag v-else color="success" class="precheck-badge">
        {{ t('core.themeStore.upload.precheck.passedBadge') }}
      </a-tag>
    </div>

    <div class="precheck-list">
      <div
        v-for="item in result.items"
        :key="item.id"
        class="precheck-row"
        :class="`precheck-row--${item.severity}`"
      >
        <span class="precheck-left">
          <CheckCircleOutlined v-if="item.severity === 'pass'" class="precheck-icon-pass" />
          <ExclamationCircleOutlined
            v-else-if="item.severity === 'warning'"
            class="precheck-icon-warn"
          />
          <CloseCircleOutlined v-else class="precheck-icon-error" />
          <span class="precheck-item-title">{{ t(item.titleKey) }}</span>
        </span>
        <span class="precheck-detail">{{ t(item.detailKey, item.params ?? {}) }}</span>
      </div>
    </div>

    <a-alert
      v-if="result.hasBlockingError"
      type="error"
      show-icon
      :message="t('core.themeStore.upload.precheck.blockedHint')"
    />
  </section>
</template>

<style scoped>
.precheck-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.precheck-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.precheck-title {
  color: var(--ant-color-text);
  font-weight: 600;
}

.precheck-badge {
  margin-inline-end: 0;
}

.precheck-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.precheck-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: var(--ant-color-fill-tertiary);
  font-size: 12px;
}

.precheck-row--error {
  border-color: var(--ant-color-error-border);
  background: var(--ant-color-error-bg);
}

.precheck-row--warning {
  border-color: var(--ant-color-warning-border);
  background: var(--ant-color-warning-bg);
}

.precheck-left {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.precheck-item-title {
  color: var(--ant-color-text);
  font-weight: 500;
}

.precheck-detail {
  color: var(--ant-color-text-secondary);
}

.precheck-icon-pass {
  color: var(--ant-color-success);
}

.precheck-icon-warn {
  color: var(--ant-color-warning);
}

.precheck-icon-error {
  color: var(--ant-color-error);
}
</style>
