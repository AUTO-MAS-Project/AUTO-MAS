<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import { AppstoreOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import arknightsNoteImage from '@/assets/community-notes/arknights.png'
import endfieldNoteImage from '@/assets/community-notes/endfield.jpg'
import genshinNoteImage from '@/assets/community-notes/genshin.jpg'
import starRailNoteImage from '@/assets/community-notes/star-rail.jpg'
import zenlessNoteImage from '@/assets/community-notes/zenless.jpg'
import type { ActivitySnapshot } from '@/views/gamesign/useCommunityActivityApi'
import { presentActivity } from '@/views/gamesign/communityActivityPresentation'

const props = defineProps<{ snapshot: ActivitySnapshot; loading: boolean }>()
defineEmits<{ refresh: [] }>()
const { t, locale } = useI18n()
const presentation = computed(() => presentActivity(props.snapshot))
const otherMetrics = computed(() => presentation.value.groups.flatMap(group => group.metrics))

// 复用游戏社区便笺卡的本地图标；中文键为后端游戏枚举。
const NOTE_IMAGES: Record<string, string> = {
  明日方舟: arknightsNoteImage,
  终末地: endfieldNoteImage,
  原神: genshinNoteImage,
  星穹铁道: starRailNoteImage,
  绝区零: zenlessNoteImage,
}

const NOTE_ACCENTS: Record<string, string> = {
  明日方舟: 'var(--ant-color-primary)',
  终末地: 'var(--ant-color-success)',
  原神: '#8fe3b0',
  星穹铁道: '#62c4e7',
  绝区零: '#ffd24a',
}

const formatTime = (value: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(locale.value, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

const platformLabel = (platform: string) => {
  if (platform === '森空岛') return t('gamesign.activity.platform.skland')
  if (platform === '米游社') return t('gamesign.activity.platform.miyoushe')
  return platform
}

const STATUS_COLORS: Record<string, string> = {
  success: 'success',
  empty: 'default',
  limited: 'warning',
  unavailable: 'orange',
  failed: 'error',
}

const statusMeta = (snapshot: ActivitySnapshot) => ({
  label: t(`gamesign.activity.status.${snapshot.status}`),
  color: STATUS_COLORS[snapshot.status] ?? 'default',
})

const alertType = (snapshot: ActivitySnapshot) => {
  if (snapshot.status === 'failed') return 'error'
  if (['limited', 'unavailable'].includes(snapshot.status)) return 'warning'
  return 'info'
}

const stripStyle = (snapshot: ActivitySnapshot): CSSProperties => ({
  '--note-accent': NOTE_ACCENTS[snapshot.game] ?? 'var(--ant-color-primary)',
})
</script>

<template>
  <article class="note-strip" :style="stripStyle(snapshot)">
    <header class="note-strip-header">
      <span class="note-game-mark">
        <img
          v-if="NOTE_IMAGES[snapshot.game]"
          class="note-game-image"
          :src="NOTE_IMAGES[snapshot.game]"
          alt=""
        />
        <AppstoreOutlined v-else aria-hidden="true" />
      </span>
      <div class="note-strip-title">
        <strong>{{ snapshot.game }}</strong>
        <span>{{ t('home.activityNotes.title') }}</span>
      </div>
      <span class="note-strip-identity">
        <slot name="identity">
          {{ platformLabel(snapshot.platform)
          }}<template v-if="snapshot.account"> · {{ snapshot.account }}</template>
        </slot>
      </span>
      <a-tag :color="statusMeta(snapshot).color">
        {{ statusMeta(snapshot).label }}
      </a-tag>
      <a-tooltip :title="t('gamesign.activity.refresh')">
        <a-button
          type="text"
          size="small"
          shape="circle"
          :loading="loading"
          :aria-label="t('gamesign.activity.refresh')"
          @click="$emit('refresh')"
        >
          <ReloadOutlined />
        </a-button>
      </a-tooltip>
    </header>

    <div v-if="presentation.featured.length || otherMetrics.length" class="note-strip-metrics">
      <div
        v-for="metric in presentation.featured"
        :key="`featured-${metric.name}`"
        class="note-metric is-featured"
      >
        <span class="note-metric-name">{{ metric.name }}</span>
        <strong v-if="metric.target > 0" class="note-metric-value">
          {{ metric.current }}<small> / {{ metric.target }}</small>
        </strong>
        <span v-if="metric.status" class="note-metric-status">{{ metric.status }}</span>
      </div>
      <div
        v-for="metric in otherMetrics"
        :key="`${metric.period}-${metric.name}`"
        class="note-metric"
      >
        <span class="note-metric-name">{{ metric.name }}</span>
        <strong v-if="metric.target > 0" class="note-metric-value">
          {{ metric.current }}<small> / {{ metric.target }}</small>
        </strong>
        <span v-if="metric.status" class="note-metric-status">{{ metric.status }}</span>
      </div>
    </div>

    <a-alert
      v-if="snapshot.reason"
      :type="alertType(snapshot)"
      :message="snapshot.reason"
      show-icon
      class="note-strip-reason"
    />
    <footer v-if="formatTime(snapshot.updatedAt)" class="note-strip-footer">
      {{ t('gamesign.activity.queriedAt', { time: formatTime(snapshot.updatedAt) }) }}
    </footer>
  </article>
</template>

<style scoped>
.note-strip {
  --note-accent: var(--ant-color-primary);
  padding: 4px 0;
  background: var(--ant-color-bg-container);
}

.note-strip-header {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.note-game-mark {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  color: var(--note-accent);
  font-size: 16px;
}

.note-game-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.note-strip-title {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  white-space: nowrap;
}

.note-strip-title strong {
  font-size: 14px;
}

.note-strip-title span {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.note-strip-identity {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-strip-metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 20px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.note-metric {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}

.note-metric-name {
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.note-metric-value {
  color: var(--ant-color-text);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.note-metric-value small {
  color: var(--ant-color-text-secondary);
  font-size: 11px;
  font-weight: 400;
}

.note-metric.is-featured .note-metric-name {
  color: var(--ant-color-text);
  font-weight: 500;
}

.note-metric.is-featured .note-metric-value {
  font-size: 15px;
}

.note-metric-status {
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.note-strip-reason {
  margin-top: 8px;
  padding: 4px 8px;
}

.note-strip-reason :deep(.ant-alert-message) {
  font-size: 12px;
  line-height: 1.35;
}

.note-strip-footer {
  margin-top: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
  text-align: right;
}

@media (max-width: 600px) {
  .note-strip-header {
    flex-wrap: wrap;
  }

  .note-strip-identity {
    flex-basis: 100%;
    order: 1;
  }
}
</style>
