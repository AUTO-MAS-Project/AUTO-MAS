<template>
  <div class="activity-stage-section">
    <!-- 摘要条：状态机压缩版，收起不丢信息；刷新按钮独立于展开按钮（按钮不可嵌套） -->
    <div class="section-header">
      <button class="section-head" type="button" @click="onToggle">
        <CaretRightOutlined class="chev" :class="{ open: !collapsed }" />
        <span class="section-title">{{ t('plan.activity.title') }}</span>
        <span v-if="period === 'ongoing'" class="live-dot">
          <span class="dot"></span>{{ t('plan.activity.ongoing') }}
        </span>
        <span v-if="summaryActivityName" class="activity-name">{{ summaryActivityName }}</span>
        <span class="summary-pill" :class="{ warn: warningCount > 0 }">{{ summaryText }}</span>
        <span class="meta">{{ metaText }}</span>
      </button>
      <a-tooltip :title="t('plan.activity.refresh')">
        <a-button
          type="text"
          size="small"
          :loading="loading"
          :aria-label="t('plan.activity.refresh')"
          @click="loadData"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </a-tooltip>
    </div>

    <div v-if="!collapsed" class="section-body">
      <div v-if="loading" class="section-loading">
        <a-spin />
      </div>
      <a-alert v-else-if="error" type="error" :message="error" show-icon>
        <template #action>
          <a-button size="small" danger @click="loadData">
            {{ t('plan.activity.retry') }}
          </a-button>
        </template>
      </a-alert>
      <template v-else>
        <p class="hint">{{ t('plan.activity.hint') }}</p>

        <a-alert
          v-if="period === 'preview' && previewMeta"
          type="info"
          class="gap-banner"
          show-icon
        >
          <template #message>
            {{
              t('plan.activity.previewBanner', {
                name: previewMeta.name,
                start: previewMeta.startText,
              })
            }}
          </template>
        </a-alert>
        <a-alert v-else-if="period === 'gap'" type="info" class="gap-banner" show-icon>
          <template #message>{{ t('plan.activity.gapBanner') }}</template>
        </a-alert>

        <ActivitySlotTable
          :rows="slotViewRows"
          :saving="saving"
          @assign="assignUser"
          @remove="removeUser"
        />

        <div v-if="ghostUsers.length" class="unassigned">
          {{ t('plan.activity.notFollowing') }}
          <span v-for="user in ghostUsers" :key="user.userId" class="ghost-chip">
            {{ user.userName }} · {{ user.planLabel }}
          </span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
// 活动关批量指派的计划表页区块：只负责折叠、摘要条与三种期间态的呈现；
// 数据、槽位行与状态文案由 useActivityStageAssignment 提供，表格在 ActivitySlotTable。
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CaretRightOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import ActivitySlotTable from './ActivitySlotTable.vue'
import { useActivityStageAssignment } from './useActivityStageAssignment'

const props = defineProps<{
  planId: string
  /** 计划表 id → 名称映射，用于未跟随用户的归属标注 */
  planNames?: Record<string, string>
}>()

const { t } = useI18n()
const {
  loading,
  error,
  saving,
  period,
  ghostUsers,
  slotViewRows,
  previewMeta,
  summaryActivityName,
  summaryText,
  metaText,
  warningCount,
  loadData,
  assignUser,
  removeUser,
} = useActivityStageAssignment(props)

// 折叠状态只记会话内组件状态（方案 §4.1，不进 localStorage）
const collapsed = ref(true)
const userTouched = ref(false)

const onToggle = () => {
  userTouched.value = true
  collapsed.value = !collapsed.value
}

// 出现需关注事项时自动展开一次（会话内一次性，不覆盖用户手动收起）
watch(
  [loading, warningCount],
  ([isLoading, warnings]) => {
    if (!isLoading && warnings > 0 && !userTouched.value && collapsed.value) {
      collapsed.value = false
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.activity-stage-section {
  margin-bottom: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  padding: 8px 16px 4px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  background: none;
  border: none;
  padding: 4px 0 8px;
  color: inherit;
  text-align: left;
  font: inherit;
  cursor: pointer;
  flex-wrap: wrap;
}

.section-head .chev {
  color: var(--ant-color-text-tertiary);
  transition: transform 0.2s;
}

.section-head .chev.open {
  transform: rotate(90deg);
}

.section-head:hover .section-title {
  color: var(--ant-color-primary);
}

.section-title {
  font-size: 15px;
  font-weight: 600;
}

.live-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ant-color-success);
  background: var(--ant-color-success-bg);
  border-radius: 4px;
  padding: 1px 8px;
}

.live-dot .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-success);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}

.activity-name {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.summary-pill {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-tertiary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  padding: 1px 10px;
  white-space: nowrap;
}

.summary-pill.warn {
  color: var(--ant-color-warning);
  border-color: var(--ant-color-warning-border);
}

.section-head .meta {
  font-size: 12px;
  color: var(--ant-color-text-quaternary);
}

.section-body {
  padding: 2px 0 12px;
}

.section-loading {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin: 0 0 12px;
}

.gap-banner {
  margin-bottom: 12px;
}

.unassigned {
  margin-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
  padding-top: 10px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.ghost-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px dashed var(--ant-color-border);
  color: var(--ant-color-text-tertiary);
  border-radius: 16px;
  padding: 2px 10px;
  font-size: 12px;
}
</style>
