<template>
  <Teleport to="body">
    <div v-if="visible" class="app-closing-overlay">
      <div class="closing-content">
        <div class="closing-spinner">
          <a-spin size="large" />
        </div>
        <div class="closing-text">{{ t('comp.closingBackend') }}</div>
        <div class="closing-subtitle">{{ t('comp.pleaseWaitAppClosing') }}</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  visible: boolean
}>()
</script>

<style scoped>
.app-closing-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease-out;
}

.closing-content {
  text-align: center;
  color: white;
  padding: 32px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  min-width: 280px;
}

.closing-spinner {
  margin-bottom: 16px;
}

.closing-text {
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 8px;
  color: #ffffff;
}

.closing-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
