<template>
  <div class="statistics-card">
    <a-tabs
      v-if="hasMultipleStatistics"
      v-model:active-key="activeStatistics"
      :animated="false"
      class="statistics-tabs"
      size="small"
    >
      <a-tab-pane v-for="option in availableStatistics" :key="option.value" :tab="option.label" />
    </a-tabs>

    <div class="card-content">
      <template v-if="activeStatistics === 'maa' && hasMaaStatistics">
        <!-- 公招统计 -->
        <div
          v-if="recruitStatistics && Object.keys(recruitStatistics).length > 0"
          class="stat-section"
        >
          <div class="stat-section-header">
            <TeamOutlined class="section-icon" />
            <span class="section-title">{{ t('history.stats.recruit') }}</span>
          </div>
          <div class="stat-items">
            <template v-for="(count, star, index) in recruitStatistics" :key="star">
              <div class="stat-item">
                <div class="stat-label" :class="`star-${star}`">{{ star }}</div>
                <div class="stat-value">{{ count }}</div>
              </div>
              <a-divider
                v-if="index < Object.keys(recruitStatistics).length - 1"
                type="vertical"
                class="stat-divider"
              />
            </template>
          </div>
        </div>

        <a-divider
          v-if="hasRecruitStatistics && hasDropStatistics"
          type="vertical"
          class="section-divider"
        />

        <!-- 掉落统计 -->
        <div v-if="dropStatistics && Object.keys(dropStatistics).length > 0" class="stat-section">
          <div class="stat-section-header">
            <GiftOutlined class="section-icon" />
            <span class="section-title">{{ t('history.stats.drops') }}</span>
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
      </template>

      <template v-else-if="activeStatistics === 'maaend' && hasMaaEndStatistics">
        <div v-if="pullCountStatistics" class="stat-section">
          <div class="stat-section-header">
            <BarChartOutlined class="section-icon" />
            <span class="section-title">{{ t('history.stats.pulls') }}</span>
          </div>
          <div class="pull-count-items">
            <div class="pull-count-item primary">
              <span>{{ t('history.stats.currentAvailable') }}</span>
              <strong>{{ pullCountStatistics.current_pool_total }}</strong>
              <span>{{ t('history.stats.pullUnit') }}</span>
            </div>
            <div class="pull-count-item">
              <span>{{ t('history.stats.nextTotal') }}</span>
              <strong>{{ pullCountStatistics.next_pool_total }}</strong>
              <span>{{ t('history.stats.pullUnit') }}</span>
            </div>
            <div class="pull-count-item compact">
              <span>{{ t('history.stats.resourcePulls', { n: pullCountStatistics.resource_pulls }) }}</span>
              <span>{{ t('history.stats.voucherPulls', { n: pullCountStatistics.carry_over_pulls }) }}</span>
            </div>
          </div>
        </div>

        <a-divider
          v-if="pullCountStatistics && hasMatrixStatistics"
          type="vertical"
          class="section-divider"
        />

        <div v-if="hasMatrixStatistics" class="stat-section">
          <div class="stat-section-header">
            <InboxOutlined class="section-icon" />
            <span class="section-title">{{ t('history.stats.matrix') }}</span>
          </div>
          <div
            v-if="matrixStatistics && Object.keys(matrixStatistics).length > 0"
            class="drop-container"
          >
            <div class="drop-stages">
              <a-popover
                v-for="(weapon, skill) in matrixStatistics"
                :key="skill"
                placement="bottom"
                trigger="hover"
              >
                <template #content>
                  <div class="drop-popover-content">
                    <div class="popover-stage-title">{{ weapon }}</div>
                    <div class="popover-drops">
                      <div class="popover-drop-item">
                        <span class="popover-item-name">{{ skill }}</span>
                      </div>
                    </div>
                  </div>
                </template>
                <div class="stage-card">
                  <div class="stage-name">{{ weapon }}</div>
                </div>
              </a-popover>
            </div>
          </div>
          <div v-else class="matrix-empty">{{ t('history.stats.noMatrix') }}</div>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-else class="empty-stats">
        <img src="@/assets/NoData.png" :alt="t('history.noData')" class="empty-image" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BarChartOutlined, GiftOutlined, InboxOutlined, TeamOutlined } from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'
import type { PullCountStatistics } from '@/types/history'

interface Props {
  recruitStatistics: Record<string, number> | null
  dropStatistics: Record<string, Record<string, number>> | null
  matrixStatistics: Record<string, string> | null
  pullCountStatistics: PullCountStatistics | null
}

const props = defineProps<Props>()

type StatisticsType = 'maa' | 'maaend'

const activeStatistics = ref<StatisticsType>('maa')

const hasRecruitStatistics = computed(() => {
  return !!props.recruitStatistics && Object.keys(props.recruitStatistics).length > 0
})

const hasDropStatistics = computed(() => {
  return !!props.dropStatistics && Object.keys(props.dropStatistics).length > 0
})

const hasMatrixStatistics = computed(() => {
  return props.matrixStatistics !== null
})

const hasMaaEndStatistics = computed(() => {
  return hasMatrixStatistics.value || props.pullCountStatistics !== null
})

const hasMaaStatistics = computed(() => {
  return hasRecruitStatistics.value || hasDropStatistics.value
})

const availableStatistics = computed(() => {
  const options: Array<{ label: string; value: StatisticsType }> = []

  if (hasMaaStatistics.value) {
    options.push({ label: 'MAA', value: 'maa' })
  }
  if (hasMaaEndStatistics.value) {
    options.push({ label: 'MaaEnd', value: 'maaend' })
  }

  return options
})

const hasMultipleStatistics = computed(() => {
  return availableStatistics.value.length > 1
})

watch(
  availableStatistics,
  options => {
    if (!options.some(option => option.value === activeStatistics.value)) {
      activeStatistics.value = options[0]?.value ?? 'maa'
    }
  },
  { immediate: true }
)

const { t } = useI18n()
</script>

<style scoped>
.statistics-card {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border: 1px solid var(--ant-color-border-secondary);
}

.statistics-tabs {
  margin: -4px 0 12px;
}

.statistics-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 12px;
}

.statistics-tabs :deep(.ant-tabs-tab) {
  padding: 8px 4px;
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

.stat-section-header {
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

.pull-count-items {
  display: flex;
  align-items: stretch;
  gap: 8px;
}

.pull-count-item {
  min-width: 104px;
  padding: 8px 12px;
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 6px;
}

.pull-count-item strong {
  color: var(--ant-color-text);
  font-size: 20px;
}

.pull-count-item.primary strong {
  color: var(--ant-color-primary);
}

.pull-count-item.compact {
  min-width: 130px;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
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

.matrix-empty {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  padding: 10px 12px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 6px;
}
</style>
