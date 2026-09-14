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

    <!-- 卡池大横幅撤掉了，改成和活动一样的小行，避免和上方的轮播横幅重复一张大图 -->
    <section v-if="overview.Pools.length" class="activity-section">
      <div class="activity-section-header">
        <span>{{ t('home.endfield.poolSection') }}</span>
      </div>

      <div class="activity-grid">
        <div v-for="pool in overview.Pools" :key="pool.Id" class="activity-item">
          <div class="activity-thumbnail">
            <PictureOutlined
              v-if="!pool.ImageUrl || failedImageIds.has(pool.Id)"
              class="activity-placeholder"
            />
            <img
              v-if="pool.ImageUrl && !failedImageIds.has(pool.Id)"
              :src="pool.ImageUrl"
              :alt="pool.UpCharacters.join('、') || pool.Name"
              @error="handleImageError(pool.Id)"
            />
          </div>

          <div class="activity-info">
            <div class="activity-title-row">
              <span class="activity-name">{{ pool.Name }}</span>
              <a-tag v-if="pool.Type" color="blue">{{ pool.Type }}</a-tag>
            </div>
            <div v-if="pool.UpCharacters.length" class="pool-up">
              {{ t('home.endfield.upCharacters', { names: pool.UpCharacters.join('、') }) }}
            </div>
            <div class="activity-meta">
              <span>{{ t('home.endfield.endsAt', { time: formatShortTime(pool.EndTime) }) }}</span>
              <a-statistic-countdown
                :value="getCountdownValue(pool.EndTime)"
                :format="t('home.countdown.dh')"
                :value-style="activityCountdownValueStyle"
                @finish="emit('refresh')"
              />
            </div>
          </div>
        </div>
      </div>
    </section>

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
import { PictureOutlined } from '@ant-design/icons-vue'
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

const activityCountdownValueStyle: CSSProperties = {
  color: 'var(--ant-color-primary)',
  fontSize: '13px',
  fontWeight: 600,
}

const { t } = useI18n()

const emptyDescription = computed(() =>
  props.overview.Available ? t('home.empty.endfield') : t('home.empty.endfieldNoData')
)

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
.activity-section-header,
.activity-title-row,
.activity-meta {
  display: flex;
  align-items: center;
}

.card-title {
  gap: 8px;
}

.source-link,
.activity-count,
.activity-meta {
  font-size: 13px;
}

.status-alert {
  margin-bottom: 16px;
}

.pool-up,
.activity-count,
.activity-meta {
  color: var(--ant-color-text-secondary);
}

.pool-up {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  .activity-item {
    grid-template-columns: 88px minmax(0, 1fr);
  }
}
</style>
