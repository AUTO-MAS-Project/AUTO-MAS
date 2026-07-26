<template>
  <div class="statistics-card" :class="{ 'statistics-card--compact': compact }">
    <div class="card-content" :class="{ 'card-content--compact': compact }">
      <!-- 公招统计 -->
      <div
        v-if="recruitStatistics && Object.keys(recruitStatistics).length > 0"
        class="stat-section"
      >
        <div class="section-header">
          <TeamOutlined class="section-icon" />
          <span class="section-title">公招统计</span>
        </div>
        <div class="stat-items">
          <template v-for="(count, star, index) in recruitStatistics" :key="star">
            <div class="stat-item">
              <div class="stat-label" :class="`star-${star}`">{{ star }}</div>
              <div class="stat-value">{{ count }}</div>
            </div>
            <a-divider
              v-if="!compact && index < Object.keys(recruitStatistics).length - 1"
              type="vertical"
              class="stat-divider"
            />
          </template>
        </div>
      </div>

      <!-- 分割线（仅非 compact 模式） -->
      <a-divider
        v-if="
          !compact &&
          recruitStatistics &&
          Object.keys(recruitStatistics).length > 0 &&
          dropStatistics &&
          Object.keys(dropStatistics).length > 0
        "
        type="vertical"
        class="section-divider"
      />

      <!-- 掉落统计 -->
      <div v-if="dropStatistics && Object.keys(dropStatistics).length > 0" class="stat-section">
        <div class="section-header">
          <GiftOutlined class="section-icon" />
          <span class="section-title">掉落统计</span>
        </div>
        <div class="drop-container">
          <div class="drop-stages">
            <a-popover
              v-for="(items, stage) in dropStatistics"
              :key="stage"
              placement="bottom"
              trigger="hover"
            >
              <template #content>
                <div class="drop-popover-content">
                  <div class="popover-stage-title">{{ stage }}</div>
                  <div class="popover-drops">
                    <div v-for="(count, item) in items" :key="item" class="popover-drop-item">
                      <span class="popover-item-name">{{ item }}</span>
                      <span class="popover-item-count">×{{ count }}</span>
                    </div>
                  </div>
                </div>
              </template>
              <div class="stage-card">
                <div class="stage-name">{{ stage }}</div>
              </div>
            </a-popover>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <EmptyState
        v-if="
          (!recruitStatistics || Object.keys(recruitStatistics).length === 0) &&
          (!dropStatistics || Object.keys(dropStatistics).length === 0)
        "
        class="empty-stats"
        :class="{ 'empty-stats--compact': compact }"
        title="暂无统计"
        compact
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { GiftOutlined, TeamOutlined } from '@ant-design/icons-vue'
import EmptyState from '@/components/v6/EmptyState.vue'

interface Props {
  recruitStatistics: Record<string, number> | null
  dropStatistics: Record<string, Record<string, number>> | null
  /** 紧凑模式：用于 Inspector 面板等窄容器，纵向堆叠并去除自带卡片样式 */
  compact?: boolean
}

withDefaults(defineProps<Props>(), {
  compact: false,
})
</script>

<style scoped>
.statistics-card {
  background: var(--v6-color-surface);
  border-radius: var(--v6-radius-card);
  padding: var(--v6-space-3) var(--v6-space-4);
  margin-bottom: var(--v6-space-4);
  border: 1px solid var(--v6-color-border-subtle);
  box-shadow: var(--v6-shadow-card);
}

/* compact 模式：去除自带卡片样式，由 Inspector section 提供容器 */
.statistics-card--compact {
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 0;
  margin-bottom: 0;
  border-radius: 0;
}

.card-content {
  display: flex;
  gap: 0;
  align-items: flex-start;
}

/* compact 模式：纵向堆叠，适配 Inspector 窄容器 */
.card-content--compact {
  flex-direction: column;
  gap: var(--v6-space-3);
}

.section-divider {
  height: auto;
  margin: 0 var(--v6-space-5);
  align-self: stretch;
}

.stat-section {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
}

.stat-section:first-child {
  flex-shrink: 0;
  width: auto;
}

.stat-section:last-of-type {
  flex: 1;
  min-width: 0;
}

/* compact 模式：每个 section 占满宽度 */
.card-content--compact .stat-section {
  width: 100%;
  flex-shrink: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

.section-icon {
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-info);
}

.section-title {
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.stat-items {
  display: flex;
  align-items: center;
  gap: 0;
}

/* compact 模式：公招条目换行以适配窄容器 */
.card-content--compact .stat-items {
  flex-wrap: wrap;
  gap: var(--v6-space-1);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v6-space-1);
  padding: var(--v6-space-1) var(--v6-space-4);
  background: var(--v6-vibrancy-hover);
  border-radius: var(--v6-radius-control);
}

/* compact 模式：缩小公招条目内边距 */
.card-content--compact .stat-item {
  padding: var(--v6-space-1) var(--v6-space-2);
  min-width: 48px;
}

.stat-item:hover {
  background: var(--v6-color-info-bg);
}

.stat-divider {
  height: 32px;
  margin: 0 var(--v6-space-3);
}

.stat-label {
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-medium);
  color: var(--v6-color-text-secondary);
}

.stat-label.star-1★,
.stat-label.star-2★,
.stat-label.star-3★ {
  color: var(--v6-color-text-tertiary);
}

.stat-label.star-4★ {
  color: var(--v6-color-warning);
}

.stat-label.star-5★ {
  color: var(--v6-color-warning);
}

.stat-label.star-6★ {
  color: var(--v6-color-error);
  font-weight: var(--v6-font-weight-semibold);
}

.stat-value {
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  font-variant-numeric: tabular-nums;
}

/* compact 模式：缩小数值字号 */
.card-content--compact .stat-value {
  font-size: var(--v6-font-size-base);
}

.drop-container {
  width: 100%;
}

.drop-stages {
  display: flex;
  gap: var(--v6-space-3);
  overflow-x: auto;
  overflow-y: hidden;
  padding: var(--v6-space-1) 0;
}

/* compact 模式：缩小 stage 卡片间距 */
.card-content--compact .drop-stages {
  gap: var(--v6-space-2);
  flex-wrap: wrap;
}

.drop-stages::-webkit-scrollbar {
  height: 6px;
}

.drop-stages::-webkit-scrollbar-track {
  background: var(--v6-vibrancy-hover);
  border-radius: var(--v6-radius-sm);
}

.drop-stages::-webkit-scrollbar-thumb {
  background: var(--v6-color-border);
  border-radius: var(--v6-radius-sm);
}

.drop-stages::-webkit-scrollbar-thumb:hover {
  background: var(--v6-color-border-strong);
}

.stage-card {
  flex-shrink: 0;
  min-width: auto;
  padding: var(--v6-space-2) var(--v6-space-4);
  background: var(--v6-vibrancy-hover);
  border-radius: var(--v6-radius-control);
  border: 1px solid var(--v6-color-border);
  cursor: pointer;
  transition:
    background-color var(--v6-motion-fast) var(--v6-ease-out),
    border-color var(--v6-motion-fast) var(--v6-ease-out);
}

/* compact 模式：缩小 stage 卡片内边距 */
.card-content--compact .stage-card {
  padding: var(--v6-space-1) var(--v6-space-2);
}

.stage-card:hover {
  background: var(--v6-color-info-bg);
  border-color: var(--v6-color-info);
}

.stage-name {
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  white-space: nowrap;
}

/* compact 模式：缩小 stage 名称字号 */
.card-content--compact .stage-name {
  font-size: var(--v6-font-size-xs);
}

.drop-popover-content {
  max-width: 300px;
  max-height: 400px;
  overflow-y: auto;
}

.popover-stage-title {
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  margin-bottom: var(--v6-space-2);
  padding-bottom: var(--v6-space-1);
  border-bottom: 1px solid var(--v6-color-border);
}

.popover-drops {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-1);
}

.popover-drop-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--v6-space-1) var(--v6-space-2);
  background: var(--v6-vibrancy-hover);
  border-radius: var(--v6-radius-sm);
  font-size: var(--v6-font-size-xs);
}

.popover-item-name {
  color: var(--v6-color-text);
  font-weight: var(--v6-font-weight-medium);
}

.popover-item-count {
  color: var(--v6-color-info);
  font-weight: var(--v6-font-weight-semibold);
  margin-left: var(--v6-space-3);
}

.empty-stats {
  width: 100%;
  padding: var(--v6-space-4);
}

.empty-stats--compact {
  padding: var(--v6-space-2);
}

@media (prefers-reduced-motion: reduce) {
  .stage-card {
    transition: none;
  }
}
</style>
