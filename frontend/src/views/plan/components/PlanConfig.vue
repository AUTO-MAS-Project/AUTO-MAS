<template>
  <a-card class="plan-config-card" :bordered="false">
    <template #title>
      <div class="plan-title-container">
        <div v-if="!isEditingPlanName" class="plan-title-display">
          <span class="plan-title-text">{{ currentPlanName || '计划配置' }}</span>
          <a-button
            type="text"
            size="small"
            @click="$emit('start-edit-plan-name')"
            class="plan-edit-btn"
          >
            <template #icon>
              <EditOutlined />
            </template>
          </a-button>
        </div>
        <div v-else class="plan-title-edit">
          <a-input
            :value="currentPlanName"
            @update:value="$emit('update:current-plan-name', $event)"
            placeholder="请输入计划名称"
            class="plan-title-input"
            @blur="$emit('finish-edit-plan-name')"
            @pressEnter="$emit('finish-edit-plan-name')"
            :maxlength="50"
            ref="planNameInputRef"
          />
        </div>
      </div>
    </template>
    <template #extra>
      <a-space>
        <span class="mode-label">执行模式：</span>
        <a-segmented
          :value="currentMode"
          @change="handleModeChange"
          :options="[
            { label: '全局模式', value: 'ALL' },
            { label: '周计划模式', value: 'Weekly' },
          ]"
        />
        <span class="view-label">视图：</span>
        <a-segmented
          :value="viewMode"
          @change="$emit('update:view-mode', $event)"
          :options="[
            { label: '配置视图', value: 'config' },
            { label: '简化视图', value: 'simple' },
          ]"
        />
      </a-space>
    </template>

    <!-- 配置表格容器 -->
    <div class="config-table-container">
      <slot />
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { EditOutlined } from '@ant-design/icons-vue'

interface Props {
  currentPlanName: string
  currentMode: 'ALL' | 'Weekly'
  viewMode: 'config' | 'simple'
  isEditingPlanName: boolean
}

interface Emits {
  (e: 'update:current-plan-name', value: string): void

  (e: 'update:current-mode', value: 'ALL' | 'Weekly'): void

  (e: 'update:view-mode', value: 'config' | 'simple'): void

  (e: 'start-edit-plan-name'): void

  (e: 'finish-edit-plan-name'): void

  (e: 'mode-change'): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

const handleModeChange = (value: 'ALL' | 'Weekly') => {
  emit('update:current-mode', value)
  emit('mode-change')
}
</script>

<style scoped>
.plan-config-card {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
}

.mode-label,
.view-label {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  font-weight: 500;
}

.plan-title-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.plan-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-title-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.plan-edit-btn {
  color: var(--ant-color-primary);
  padding: 0;
}

.plan-title-input {
  flex: 1;
  max-width: 400px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.config-table-container {
  border-radius: 8px;
  overflow: hidden;
  /* border: 1px solid var(--ant-color-border-secondary); */
}

/* 深度样式 */
.plan-config-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 16px 24px;
}

.plan-config-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.plan-title-input :deep(.ant-input) {
  font-size: 16px;
  font-weight: 500;
}

.plan-title-input :deep(.ant-input:focus) {
  box-shadow: 0 0 0 2px var(--ant-color-primary);
}

@media (max-width: 768px) {
  .plan-title-input {
    max-width: 100%;
  }
}
</style>
