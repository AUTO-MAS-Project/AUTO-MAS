<template>
  <a-card class="endfield-card" :loading="loading">
    <template #title>
      <div class="card-title">
        <span>{{ t('home.module.endfield') }}</span>
        <a-tag v-if="overview.Stale" color="orange">{{ t('home.endfield.stale') }}</a-tag>
      </div>
    </template>

    <template #extra>
      <a-typography-link
        :href="overview.SourceUrl"
        target="_blank"
        rel="noreferrer"
        class="source-link"
        @click="handleExternalLink"
      >
        {{ t('home.endfield.source', { name: overview.SourceName }) }}
      </a-typography-link>
    </template>

    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <a-carousel
      v-if="overview.Pools.length"
      class="pool-carousel"
      :dots="overview.Pools.length > 1"
    >
      <div v-for="pool in overview.Pools" :key="pool.Id">
        <div class="pool-banner">
          <div class="pool-content">
            <div class="pool-heading">
              <a-tag color="blue">{{ pool.Type }}</a-tag>
              <span v-if="pool.UpCharacters.length" class="up-characters">
                UP：{{ pool.UpCharacters.join('、') }}
              </span>
            </div>
            <div class="pool-name">{{ pool.Name }}</div>
            <div class="pool-end-time">
              <ClockCircleOutlined />
              <span>{{ t('home.endfield.endsAt', { time: formatTime(pool.EndTime) }) }}</span>
            </div>
            <a-statistic-countdown
              :title="t('home.endfield.poolRemaining')"
              :value="getCountdownValue(pool.EndTime)"
              :format="t('home.countdown.dhm')"
              :value-style="poolCountdownValueStyle"
              @finish="emit('refresh')"
            />
          </div>

          <div class="pool-art">
            <PictureOutlined
              v-if="!pool.ImageUrl || failedImageIds.has(pool.Id)"
              class="pool-placeholder"
            />
            <img
              v-if="pool.ImageUrl && !failedImageIds.has(pool.Id)"
              :src="pool.ImageUrl"
              :alt="pool.UpCharacters.join('、') || pool.Name"
              @error="handleImageError(pool.Id)"
            />
          </div>
        </div>
      </div>
    </a-carousel>

    <section v-if="overview.Activities.length" class="activity-section">
      <div class="activity-section-header">
        <span>{{ t('home.endfield.concurrent') }}</span>
        <span class="activity-count">{{
          t(
            'home.endfield.ongoing',
            { count: overview.Activities.length },
            overview.Activities.length
          )
        }}</span>
      </div>

      <div class="activity-grid">
        <div v-for="activity in overview.Activities" :key="activity.Id" class="activity-item">
          <div class="activity-thumbnail">
            <PictureOutlined
              v-if="!activity.ImageUrl || failedImageIds.has(activity.Id)"
              class="activity-placeholder"
            />
            <img
              v-if="activity.ImageUrl && !failedImageIds.has(activity.Id)"
              :src="activity.ImageUrl"
              :alt="activity.Name"
              @error="handleImageError(activity.Id)"
            />
          </div>

          <div class="activity-info">
            <div class="activity-title-row">
              <span class="activity-name">{{ activity.Name }}</span>
              <a-tag v-if="activity.Tags[0]">{{ activity.Tags[0] }}</a-tag>
            </div>
            <div class="activity-meta">
              <span>{{
                t('home.endfield.endsAt', { time: formatShortTime(activity.EndTime) })
              }}</span>
              <a-statistic-countdown
                :value="getCountdownValue(activity.EndTime)"
                :format="t('home.countdown.dh')"
                :value-style="activityCountdownValueStyle"
                @finish="emit('refresh')"
              />
            </div>
          </div>
        </div>
      </div>
    </section>

    <a-empty v-else-if="!loading && !overview.Pools.length" :description="emptyDescription" />
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { ClockCircleOutlined, PictureOutlined } from '@ant-design/icons-vue'
import type { CSSProperties } from 'vue'
import type { EndfieldActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({
  name: 'HomeEndfieldOverview',
})

interface Props {
  loading: boolean
  overview: EndfieldActivityOverview
}

const props = defineProps<Props>()

const emit = defineEmits<{
  refresh: []
}>()

const failedImageIds = ref(new Set<string>())

const poolCountdownValueStyle: CSSProperties = {
  color: 'var(--ant-color-text)',
  fontSize: '28px',
  fontWeight: 700,
}

const activityCountdownValueStyle: CSSProperties = {
  color: 'var(--ant-color-primary)',
  fontSize: '13px',
  fontWeight: 600,
}

const { t } = useI18n()

const emptyDescription = computed(() =>
  props.overview.Available ? t('home.empty.endfield') : t('home.empty.endfieldNoData')
)

const formatTime = (timeString: string) => {
  return new Date(timeString).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatShortTime = (timeString: string) => {
  return new Date(timeString).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getCountdownValue = (timeString: string) => new Date(timeString).getTime()

const handleImageError = (itemId: string) => {
  failedImageIds.value.add(itemId)
}
</script>

<style scoped>
.endfield-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.endfield-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.card-title,
.pool-heading,
.pool-end-time,
.activity-section-header,
.activity-title-row,
.activity-meta {
  display: flex;
  align-items: center;
}

.card-title,
.pool-heading,
.pool-end-time {
  gap: 8px;
}

.source-link,
.activity-count,
.pool-end-time,
.activity-meta {
  font-size: 13px;
}

.status-alert {
  margin-bottom: 16px;
}

.pool-carousel {
  min-width: 0;
}

.pool-banner {
  min-height: 220px;
  padding: 28px 32px;
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 34%);
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.pool-content {
  position: relative;
  z-index: 1;
}

.up-characters,
.pool-end-time,
.activity-count,
.activity-meta {
  color: var(--ant-color-text-secondary);
}

.pool-name {
  margin: 14px 0 8px;
  color: var(--ant-color-text);
  font-size: 28px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.pool-end-time {
  margin-bottom: 16px;
}

.pool-art {
  min-height: 164px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-quaternary);
}

.pool-art img {
  width: 100%;
  height: 210px;
  position: absolute;
  inset: auto 0 -28px;
  z-index: 1;
  object-fit: contain;
  object-position: center bottom;
}

.pool-placeholder {
  z-index: 1;
  font-size: 44px;
}

.pool-carousel :deep(.slick-dots) {
  bottom: 10px;
}

.pool-carousel :deep(.slick-dots li button) {
  background: var(--ant-color-text-quaternary);
}

.pool-carousel :deep(.slick-dots li.slick-active button) {
  background: var(--ant-color-primary);
}

.activity-section {
  margin-top: 20px;
}

.activity-section-header {
  margin-bottom: 10px;
  justify-content: space-between;
  font-weight: 600;
}

.activity-count {
  font-weight: 400;
}

.activity-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.activity-item {
  min-width: 0;
  padding: 8px;
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
}

.activity-thumbnail {
  height: 52px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: var(--ant-color-text-quaternary);
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
}

.activity-thumbnail img {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  object-fit: cover;
}

.activity-placeholder {
  font-size: 20px;
}

.activity-info {
  min-width: 0;
}

.activity-title-row,
.activity-meta {
  min-width: 0;
  justify-content: space-between;
  gap: 8px;
}

.activity-name {
  min-width: 0;
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-title-row :deep(.ant-tag) {
  margin-inline-end: 0;
  flex-shrink: 0;
  font-size: 11px;
  line-height: 18px;
}

.activity-meta {
  margin-top: 7px;
}

.activity-meta :deep(.ant-statistic-content) {
  line-height: 1;
}

@media (max-width: 900px) {
  .activity-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .pool-banner {
    padding: 24px;
    grid-template-columns: 1fr;
  }

  .pool-art {
    display: none;
  }

  .pool-name {
    font-size: 24px;
  }

  .activity-item {
    grid-template-columns: 88px minmax(0, 1fr);
  }
}
</style>
