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
        <span v-if="activityName" class="activity-name">{{ activityName }}</span>
        <span class="summary-pill" :class="{ warn: summary.attention > 0 }">
          {{ summaryText }}
        </span>
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
        <p v-if="noticeText" class="period-notice">{{ noticeText }}</p>

        <ActivityUserTable
          :rows="visibleRows"
          :no-intent-count="noIntentCount"
          :summary="summary"
          :filter="filter"
          :selected-keys="selectedKeys"
          :selected-count="selectedCount"
          :all-selected="allSelected"
          :some-selected="someSelected"
          :bulk-stage-options="bulkStageOptions"
          :saving="saving"
          @select="toggleSelect"
          @select-all="toggleSelectAll"
          @toggle="setRowSwitch"
          @intent="setRowIntent"
          @bulk="applyBulk"
          @update:filter="filter = $event"
        />

        <p v-if="otherUsersCount" class="others">
          {{ t('plan.activity.others', { n: otherUsersCount }) }}
        </p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
// 活动关批量指派的计划表页区块：只负责折叠、摘要条与三种期间态的呈现；
// 数据、用户行与状态文案由 useActivityStageAssignment 提供，表格在 ActivityUserTable。
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CaretRightOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import ActivityUserTable from './ActivityUserTable.vue'
import { useActivityStageAssignment } from './useActivityStageAssignment'

const props = defineProps<{
  planId: string
}>()

const { t } = useI18n()
const {
  loading,
  saving,
  error,
  filter,
  period,
  metaText,
  summaryText,
  visibleRows,
  noIntentCount,
  summary,
  activityName,
  otherUsersCount,
  bulkStageOptions,
  selectedKeys,
  selectedCount,
  allSelected,
  someSelected,
  loadData,
  setRowIntent,
  setRowSwitch,
  applyBulk,
  toggleSelect,
  toggleSelectAll,
} = useActivityStageAssignment(props)

// 折叠状态只记组件内（方案 §4.1，不进 localStorage）：切计划表类型会重建组件，
// 届时回到默认收起
const collapsed = ref(true)
const userTouched = ref(false)

const onToggle = () => {
  userTouched.value = true
  collapsed.value = !collapsed.value
}

// 出现需关注事项时自动展开一次（每次进入页面最多一次，不覆盖用户手动收起；
// 事项未解决前每次进来都会再展开，避免问题被折叠藏住）
watch(
  [loading, () => summary.value.attention],
  ([isLoading, attention]) => {
    if (!isLoading && attention > 0 && !userTouched.value && collapsed.value) {
      collapsed.value = false
    }
  },
  { immediate: true }
)

/** 间隙期与下期预览各一句，说明本次指派按哪一期解析 */
const noticeText = computed(() => {
  if (period.value === 'preview') {
    return t('plan.activity.previewNotice')
  }
  if (period.value === 'gap') {
    return t('plan.activity.gapNotice')
  }
  return ''
})
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
  padding: 6px 0;
  cursor: pointer;
}

.chev {
  transition: transform 0.2s;
  color: var(--ant-color-text-secondary);
}

.chev.open {
  transform: rotate(90deg);
}

.section-title {
  font-weight: 600;
}

.live-dot {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-success);
  font-size: 12px;
}

.live-dot .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentcolor;
}

.activity-name {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.summary-pill {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: var(--ant-color-fill-secondary);
  color: var(--ant-color-text-secondary);
}

.summary-pill.warn {
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-warning-text);
}

.meta {
  margin-left: auto;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.section-body {
  padding: 4px 0 8px;
}

.section-loading {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.hint {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.period-notice {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.others {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
</style>
