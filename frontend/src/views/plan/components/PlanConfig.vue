<template>
  <a-card class="plan-config-card" :class="{ 'plan-config-compact': compact }" :bordered="false">
    <template #title>
      <div class="plan-title-container">
        <div v-if="!isEditingPlanName" class="plan-title-display">
          <span class="plan-title-text">{{ currentPlanName || t('plan.configTitle') }}</span>
          <a-button
            type="text"
            size="small"
            class="plan-edit-btn"
            @click="$emit('start-edit-plan-name')"
          >
            <template #icon>
              <EditOutlined />
            </template>
          </a-button>
        </div>
        <div v-else class="plan-title-edit">
          <a-input
            ref="planNameInputRef"
            :value="currentPlanName"
            :placeholder="t('plan.namePlaceholder')"
            class="plan-title-input"
            :maxlength="50"
            @update:value="$emit('update:current-plan-name', $event)"
            @blur="$emit('finish-edit-plan-name')"
            @press-enter="$emit('finish-edit-plan-name')"
          />
        </div>
      </div>
    </template>
    <template #extra>
      <a-space :wrap="compact">
        <span class="mode-label">{{ t('plan.modeLabel') }}</span>
        <a-segmented
          :value="currentMode"
          :options="[
            { label: t('plan.modeAll'), value: 'ALL' },
            { label: t('plan.modeWeekly'), value: 'Weekly' },
            { label: t('plan.modeRotate'), value: 'Rotate' },
          ]"
          @change="handleModeChange"
        />
        <!-- 只有多天轮换用得上这个天数，别的模式下摆出来会让人以为周计划也按它排 -->
        <template v-if="currentMode === 'Rotate'">
          <span class="mode-label">{{ t('plan.rotateDaysLabel') }}</span>
          <a-input-number
            :value="rotateDays"
            :min="PLAN_ROTATE_DAYS_MIN"
            :max="PLAN_ROTATE_DAYS_MAX"
            size="small"
            class="rotate-days-input"
            @update:value="handleRotateDaysChange"
          />
        </template>
        <!-- 只给提供了简化视图的类型显示这个切换，避免出现点了没反应的控件 -->
        <template v-if="supportsSimpleView">
          <span class="view-label">{{ t('plan.viewLabel') }}</span>
          <a-segmented
            :value="viewMode"
            :options="[
              { label: t('plan.viewConfig'), value: 'config' },
              { label: t('plan.viewSimple'), value: 'simple' },
            ]"
            @change="$emit('update:view-mode', $event)"
          />
        </template>
      </a-space>
    </template>

    <!-- 配置表格容器 -->
    <div class="config-table-container">
      <slot />
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { EditOutlined } from '@ant-design/icons-vue'
import {
  PLAN_ROTATE_DAYS_MAX,
  PLAN_ROTATE_DAYS_MIN,
  clampRotateDays,
  type PlanMode,
} from '@/utils/planDays'

const { t } = useI18n()

interface Props {
  currentPlanName: string
  currentMode: PlanMode
  /** 多天轮换的天数，只影响 Rotate 模式的列数 */
  rotateDays: number
  viewMode: 'config' | 'simple'
  /** 该类型是否提供简化视图；为 false 时隐藏视图切换 */
  supportsSimpleView: boolean
  isEditingPlanName: boolean
  /** 摘要表使用紧凑标题，窄窗口允许执行模式换行。 */
  compact?: boolean
}

interface Emits {
  (e: 'update:current-plan-name', value: string): void

  (e: 'update:current-mode', value: PlanMode): void

  (e: 'update:rotate-days', value: number): void

  (e: 'update:view-mode', value: 'config' | 'simple'): void

  (e: 'start-edit-plan-name'): void

  (e: 'finish-edit-plan-name'): void

  (e: 'mode-change'): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

const handleModeChange = (value: PlanMode) => {
  emit('update:current-mode', value)
  emit('mode-change')
}

const handleRotateDaysChange = (value: number | string | null) => {
  emit('update:rotate-days', clampRotateDays(value))
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

/* 轮换天数是三选一旁边的一个小数，给个固定宽度免得它随数字位数跳 */
.rotate-days-input {
  width: 72px;
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

.plan-config-compact .plan-title-container {
  margin-bottom: 0;
}

.plan-config-compact :deep(.ant-card-head) {
  padding: 12px 24px;
}

.plan-config-compact :deep(.ant-card-head-wrapper) {
  flex-wrap: wrap;
  gap: 8px;
}

.plan-config-compact :deep(.ant-card-extra) {
  margin-inline-start: 0;
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
