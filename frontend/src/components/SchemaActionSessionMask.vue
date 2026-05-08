<template>
  <teleport to="body">
    <div v-if="visible" class="schema-action-mask">
      <div class="mask-content">
        <div class="mask-icon">
          <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
        </div>
        <h2 class="mask-title">{{ title }}</h2>
        <p class="mask-description">{{ description }}</p>
        <div class="mask-actions">
          <a-button type="primary" size="large" :loading="stopping" @click="emit('stop')">
            {{ stopLabel }}
          </a-button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { SettingOutlined } from '@ant-design/icons-vue'

withDefaults(
  defineProps<{
    visible: boolean
    title?: string
    description?: string
    stopLabel?: string
    stopping?: boolean
  }>(),
  {
    title: '正在执行配置动作',
    description: '请在外部窗口完成相关设置，然后回到这里结束会话。',
    stopLabel: '结束会话',
    stopping: false,
  }
)

const emit = defineEmits<{
  (e: 'stop'): void
}>()
</script>

<style scoped>
.schema-action-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 24px;
}

.mask-content {
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
}

.mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.6;
  white-space: pre-line;
}

.mask-actions {
  display: flex;
  justify-content: center;
}
</style>
