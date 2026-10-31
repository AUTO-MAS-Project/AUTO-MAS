<template>
  <a-card :title="section.title" class="activity-section">
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          v-if="section.source"
          :href="section.source.url"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
          >{{ section.source.label }}</a-typography-link
        >
        <a-tag v-if="section.stale" color="orange">{{ t('core.home.sra.stale') }}</a-tag>
        <a-button
          v-if="section.refresh"
          type="text"
          size="small"
          :aria-label="section.refresh.label"
          :title="section.refresh.label"
          :loading="section.refresh.loading"
          :disabled="section.refresh.disabled"
          @click="emit('refresh')"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </template>
    <div
      v-if="section.choices"
      class="section-choices"
      role="group"
      :aria-label="section.choices.label"
    >
      <span>{{ section.choices.label }}</span>
      <a-button
        v-for="option in section.choices.options"
        :key="option.value"
        size="small"
        :type="option.value === section.choices.selected ? 'primary' : 'default'"
        :aria-pressed="option.value === section.choices.selected"
        @click="emit('select', option.value)"
        >{{ option.label }}</a-button
      >
    </div>
    <a-alert
      v-for="alert in section.alerts"
      :key="alert.id"
      :message="alert.message"
      :description="alert.description"
      :type="alert.type"
      :closable="alert.closable"
      show-icon
      class="status-alert"
      @close="emit('dismiss', alert.id)"
    >
      <template v-if="alert.action" #action>
        <a-button
          size="small"
          :loading="alert.action.loading"
          :disabled="alert.action.disabled"
          @click="emit('action', alert.id)"
          >{{ alert.action.label }}</a-button
        >
      </template>
    </a-alert>
    <div v-if="section.loading" class="section-loading">
      <a-skeleton active :paragraph="{ rows: 3 }" />
    </div>
    <ul
      v-else-if="section.items.length"
      class="activity-list"
      :class="`is-${section.layout ?? 'activity'}`"
    >
      <li
        v-for="item in section.items"
        :key="`${section.choices?.selected ?? ''}:${item.id}`"
        class="activity-card"
      >
        <HomeActivityEntry
          :item="item"
          :layout="section.layout"
          :accent="section.accent ?? accent"
          :time-zone="section.timeZone"
          :time-zone-label="section.timeZoneLabel"
          @action="emit('action', $event)"
          @boundary="handleBoundary"
        />
      </li>
    </ul>
    <NoData v-else-if="section.available && section.emptyText" :description="section.emptyText" />
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ReloadOutlined } from '@ant-design/icons-vue'
import type { HomeActivitySection } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'
import HomeActivityEntry from './HomeActivityEntry.vue'

defineProps<{ section: HomeActivitySection; accent: string }>()
const emit = defineEmits<{
  refresh: []
  select: [value: string]
  action: [id: string]
  dismiss: [id: string]
}>()
const { t } = useI18n()
// 相同时间的活动边界只刷新一次，各倒计时的帧回调可能分属不同微任务。
const handledBoundaries = new Set<number>()
const handleBoundary = (time: number) => {
  if (handledBoundaries.has(time)) return
  handledBoundaries.add(time)
  emit('refresh')
}
</script>

<style scoped>
.activity-section {
  min-width: 0;
}
.activity-section :deep(.ant-card-head) {
  flex-wrap: wrap;
  padding: 0 16px;
}
.activity-section :deep(.ant-card-head-wrapper) {
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0;
}
.activity-section :deep(.ant-card-head-title) {
  flex-basis: auto;
  padding: 0;
}
.activity-section :deep(.ant-card-extra) {
  padding: 0;
}
.activity-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 0;
  margin: 0;
  list-style: none;
}
.activity-card {
  min-width: 0;
}
.activity-list.is-resource {
  flex-direction: row;
  flex-wrap: wrap;
}
.is-resource > .activity-card {
  max-width: 100%;
}
.card-extra,
.section-choices {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.source-link {
  font-size: 12px;
}
.section-choices,
.status-alert {
  margin-bottom: 12px;
}
.section-loading {
  min-height: 160px;
}
</style>
