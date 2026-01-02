<template>
  <div class="statistics-card">
    <div class="card-content">
      <!-- 公招统计 -->
      <div v-if="recruitStatistics && Object.keys(recruitStatistics).length > 0" class="stat-section">
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
            <a-divider v-if="index < Object.keys(recruitStatistics).length - 1" type="vertical" class="stat-divider" />
          </template>
        </div>
      </div>

      <!-- 分割线 -->
      <a-divider
        v-if="recruitStatistics && Object.keys(recruitStatistics).length > 0 && dropStatistics && Object.keys(dropStatistics).length > 0"
        type="vertical" class="section-divider" />

      <!-- 掉落统计 -->
      <div v-if="dropStatistics && Object.keys(dropStatistics).length > 0" class="stat-section">
        <div class="section-header">
          <GiftOutlined class="section-icon" />
          <span class="section-title">掉落统计</span>
        </div>
        <div class="drop-container">
          <div class="drop-stages">
            <a-popover v-for="(items, stage) in dropStatistics" :key="stage" placement="bottom" trigger="hover">
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
      <div v-if="
        (!recruitStatistics || Object.keys(recruitStatistics).length === 0) &&
        (!dropStatistics || Object.keys(dropStatistics).length === 0)
      " class="empty-stats">
        <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { GiftOutlined, InboxOutlined, TeamOutlined } from '@ant-design/icons-vue'

interface Props {
  recruitStatistics: Record<string, number> | null
  dropStatistics: Record<string, Record<string, number>> | null
}

defineProps<Props>()
</script>

<style scoped>
.statistics-card {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border: 1px solid var(--ant-color-border-secondary);
}

.card-content {
  display: flex;
  gap: 0;
  align-items: flex-start;
}

.section-divider {
  height: auto !important;
  margin: 0 20px !important;
  align-self: stretch;
}

.stat-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stat-section:first-child {
  flex-shrink: 0;
  width: auto;
}

.stat-section:last-of-type {
  flex: 1;
  min-width: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  font-size: 14px;
  color: var(--ant-color-primary);
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.stat-items {
  display: flex;
  align-items: center;
  gap: 0;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 6px;
}

.stat-item:hover {
  background: var(--ant-color-fill-tertiary);
}

.stat-divider {
  height: 32px !important;
  margin: 0 12px !important;
}

.stat-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.stat-label.star-1★,
.stat-label.star-2★,
.stat-label.star-3★ {
  color: #8c8c8c;
}

.stat-label.star-4★ {
  color: #d48806;
}

.stat-label.star-5★ {
  color: #faad14;
}

.stat-label.star-6★ {
  color: #ff4d4f;
  font-weight: 600;
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.drop-container {
  width: 100%;
}

.drop-stages {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 0;
}

.drop-stages::-webkit-scrollbar {
  height: 6px;
}

.drop-stages::-webkit-scrollbar-track {
  background: var(--ant-color-fill-quaternary);
  border-radius: 3px;
}

.drop-stages::-webkit-scrollbar-thumb {
  background: var(--ant-color-fill-tertiary);
  border-radius: 3px;
}

.drop-stages::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-fill-secondary);
}

.stage-card {
  flex-shrink: 0;
  min-width: auto;
  padding: 8px 16px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 6px;
  border: 1px solid var(--ant-color-border);
  cursor: pointer;
  transition: all 0.2s;
}

.stage-card:hover {
  background: var(--ant-color-fill-tertiary);
  border-color: var(--ant-color-primary);
}

.stage-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text);
  white-space: nowrap;
}

.drop-popover-content {
  max-width: 300px;
  max-height: 400px;
  overflow-y: auto;
}

.popover-stage-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--ant-color-border);
}

.popover-drops {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.popover-drop-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
  font-size: 12px;
}

.popover-item-name {
  color: var(--ant-color-text);
  font-weight: 500;
}

.popover-item-count {
  color: var(--ant-color-primary);
  font-weight: 600;
  margin-left: 12px;
}

.empty-stats {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
}

.empty-image {
  width: 80px;
  height: auto;
  opacity: 0.7;
}

.empty-text {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
