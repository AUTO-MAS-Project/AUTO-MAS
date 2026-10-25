<template>
  <component
    :is="item.url && !item.action ? 'a' : 'div'"
    class="activity-item"
    :class="{
      [`is-${layout}`]: true,
      'is-fallback': !image,
      'has-image': Boolean(image),
      'is-completed': item.completed,
      'is-actionable': item.action && !item.action.disabled,
      'is-saving': item.action?.loading,
    }"
    :href="item.url && !item.action ? item.url : undefined"
    :target="item.url && !item.action ? '_blank' : undefined"
    :rel="item.url && !item.action ? 'noreferrer' : undefined"
    :role="item.action ? 'button' : undefined"
    :tabindex="item.action ? (item.action.disabled ? -1 : 0) : undefined"
    :aria-label="item.action?.label"
    :aria-pressed="item.action ? Boolean(item.completed) : undefined"
    :aria-disabled="item.action?.disabled"
    :aria-busy="item.action?.loading"
    :title="item.action?.label"
    @click="activate"
    @keydown="onKeydown"
  >
    <div v-if="layout === 'resource' && item.tags?.length" class="resource-stage">
      <span v-for="tag in item.tags" :key="tag">{{ tag }}</span>
    </div>
    <img
      v-if="image"
      :src="image"
      alt=""
      class="activity-image"
      :class="{ 'is-contained': layout === 'activity' && item.imageFit === 'contain' }"
      :style="{ objectFit: layout === 'activity' ? (item.imageFit ?? 'cover') : 'contain' }"
      loading="lazy"
      decoding="async"
      referrerpolicy="no-referrer"
      @error="failImage"
    />
    <div v-if="layout === 'activity'" class="activity-overlay" />
    <div class="activity-content">
      <div
        v-if="item.status || (layout !== 'resource' && item.tags?.length) || item.action?.loading"
        class="activity-head"
      >
        <LoadingOutlined v-if="item.action?.loading" aria-hidden="true" />
        <a-tag
          v-if="item.status"
          :color="item.status.color"
          :class="{ 'completion-tag': item.completed }"
          >{{ item.status.label }}</a-tag
        >
        <template v-if="layout !== 'resource'">
          <span v-for="tag in item.tags" :key="tag" class="activity-kind">{{ tag }}</span>
        </template>
      </div>
      <div class="activity-name">
        <a
          v-if="item.url && item.action"
          :href="item.url"
          target="_blank"
          rel="noreferrer"
          @click.stop="handleExternalLink"
          @keydown.stop
          >{{ item.name }}</a
        >
        <template v-else>{{ item.name }}</template>
      </div>
      <div v-if="item.description" class="activity-desc">{{ item.description }}</div>
      <div v-if="item.endTime" class="activity-meta">
        <div class="activity-countdown">
          <span v-if="item.countdownLabel">{{
            $t(upcoming ? 'home.countdown.startsIn' : 'home.countdown.left')
          }}</span>
          <a-statistic-countdown
            :value="targetTime"
            :format="$t(item.countdownDaysOnly ? 'home.countdown.d' : 'home.countdown.dh')"
            :value-style="countdownStyle"
            @finish="emit('boundary', targetTime)"
          />
        </div>
        <time class="activity-end-time" :datetime="target">{{ boundaryLabel }}</time>
      </div>
    </div>
    <a-progress
      v-if="item.progress !== undefined"
      class="activity-progress"
      :percent="item.progress"
      :show-info="false"
      :stroke-color="image ? accent : undefined"
      :trail-color="image ? 'rgba(255, 255, 255, 0.25)' : undefined"
      :stroke-width="4"
      stroke-linecap="butt"
      status="normal"
    />
  </component>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoadingOutlined } from '@ant-design/icons-vue'
import type { HomeActivityEntry, HomeActivityLayout } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'
import { formatActivityTime } from '@/views/home/activityTime'

const props = withDefaults(
  defineProps<{
    item: HomeActivityEntry
    layout?: HomeActivityLayout
    accent: string
    timeZone?: string
    timeZoneLabel?: string
  }>(),
  { layout: 'activity', timeZone: undefined, timeZoneLabel: undefined }
)
const emit = defineEmits<{ action: [id: string]; boundary: [time: number] }>()
const { t, locale } = useI18n()
const failedImages = ref(new Set<string>())
const image = computed(
  () =>
    [props.item.image, props.item.fallbackImage].find(url => url && !failedImages.value.has(url)) ||
    ''
)
// 数据刷新但地址未变时不重试坏图；新地址和新条目可以重新加载。
watch(
  () => [props.item.id, props.item.image, props.item.fallbackImage].join('\u0000'),
  () => {
    failedImages.value = new Set()
  }
)
const failImage = () => {
  failedImages.value = new Set(failedImages.value).add(image.value)
}
const upcoming = computed(() => new Date(props.item.startTime ?? '').getTime() > Date.now())
const target = computed(() => (upcoming.value ? props.item.startTime : props.item.endTime) ?? '')
const targetTime = computed(() => new Date(target.value).getTime())
const boundaryLabel = computed(() => {
  const time = formatActivityTime(target.value, locale.value, props.timeZone)
  const label = t(upcoming.value ? 'home.activity.startsAt' : 'home.activity.endsAt', {
    time,
  })
  return props.timeZoneLabel ? `${label} (${props.timeZoneLabel})` : label
})
const countdownStyle = computed(() => ({
  color: props.layout === 'activity' && image.value ? props.accent : 'var(--ant-color-primary)',
  fontSize: '14px',
  fontWeight: 700,
}))
const activate = (event: MouseEvent) => {
  if (props.item.action) {
    if (!props.item.action.disabled && !props.item.action.loading) emit('action', props.item.id)
  } else if (props.item.url) handleExternalLink(event)
}
const onKeydown = (event: KeyboardEvent) => {
  if (!props.item.action || (event.key !== 'Enter' && event.key !== ' ')) return
  event.preventDefault()
  if (!props.item.action.disabled && !props.item.action.loading) emit('action', props.item.id)
}
</script>

<style scoped>
.activity-item {
  position: relative;
  display: flex;
  align-items: flex-end;
  min-width: 0;
  min-height: 150px;
  overflow: hidden;
  border-radius: 10px;
  background: var(--ant-color-fill-quaternary);
  color: #fff;
}
.activity-image,
.activity-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.activity-image {
  object-fit: cover;
  transition: transform 0.25s ease;
}
.has-image {
  background: #14203a;
}
.activity-image.is-contained {
  box-sizing: border-box;
  object-position: right center;
  padding: 12px;
}
.activity-item:hover .activity-image.is-contained {
  transform: none;
}
.activity-overlay {
  background: linear-gradient(180deg, rgba(11, 18, 32, 0.05), rgba(11, 18, 32, 0.88));
}
.activity-item:hover .activity-image {
  transform: scale(1.05);
}
.activity-content {
  position: relative;
  z-index: 1;
  min-width: 0;
  width: 100%;
  padding: 14px 16px;
}
.activity-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.activity-head :deep(.ant-tag) {
  margin-inline-end: 0;
}
.activity-kind,
.activity-desc,
.activity-end-time,
.activity-countdown > span {
  font-size: 12px;
}
.activity-name {
  margin-bottom: 8px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  overflow-wrap: anywhere;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}
.activity-name a {
  color: inherit;
  text-decoration: underline;
}
.activity-desc {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  margin-bottom: 8px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.activity-item:hover .activity-desc,
.activity-item:focus-within .activity-desc {
  display: block;
}
.activity-meta,
.activity-countdown {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
}
.activity-meta {
  justify-content: space-between;
}
.activity-end-time {
  color: rgba(255, 255, 255, 0.8);
  overflow-wrap: anywhere;
}
.activity-progress {
  position: absolute;
  inset: auto 0 0;
  z-index: 2;
  width: 100%;
  margin: 0;
  line-height: 0;
}
.activity-progress :deep(.ant-progress-outer),
.activity-progress :deep(.ant-progress-inner) {
  display: block;
}
.is-fallback {
  border: 1px solid var(--ant-color-border-secondary);
  color: var(--ant-color-text);
}
.is-fallback {
  min-height: 82px;
}
.is-fallback .activity-overlay {
  display: none;
}
.is-fallback .activity-name {
  text-shadow: none;
}
.is-fallback .activity-end-time,
.is-fallback .activity-desc,
.is-fallback .activity-kind {
  color: var(--ant-color-text-secondary);
}
.is-actionable {
  cursor: pointer;
}
.is-saving {
  cursor: progress;
}
[aria-disabled='true'] {
  opacity: 0.75;
}
.is-completed .activity-image {
  filter: grayscale(1);
  opacity: 0.6;
}
.completion-tag {
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  border-color: var(--ant-color-border);
}
.activity-item:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}
.is-horizontal,
.is-resource {
  align-items: flex-start;
  gap: 12px;
  min-height: 0;
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-fill-quaternary);
}
.is-horizontal .activity-image,
.is-resource .activity-image {
  position: static;
  flex: 0 0 auto;
  width: 88px;
  height: 88px;
  border-radius: 4px;
  background: var(--ant-color-bg-container);
  transform: none;
}
.is-horizontal .activity-content,
.is-resource .activity-content {
  flex: 1;
  width: auto;
  padding: 0;
}
.is-horizontal:hover .activity-image,
.is-resource:hover .activity-image {
  transform: none;
}
.is-horizontal .activity-head {
  margin-bottom: 6px;
}
.is-horizontal .activity-name,
.is-resource .activity-name {
  text-shadow: none;
}
.is-horizontal .activity-name,
.is-horizontal .activity-desc {
  margin-bottom: 6px;
}
.is-horizontal .activity-desc,
.is-resource .activity-desc {
  display: block;
}
.is-horizontal .activity-kind,
.is-horizontal .activity-desc,
.is-horizontal .activity-end-time,
.is-resource .activity-kind,
.is-resource .activity-desc,
.is-resource .activity-end-time {
  color: var(--ant-color-text-secondary);
}
.is-horizontal .activity-meta {
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}
.is-resource {
  align-items: center;
  min-width: min(220px, 100%);
  padding: 12px 16px;
  background: var(--ant-color-bg-container);
}
.resource-stage {
  display: flex;
  flex-direction: column;
  flex: 0 1 auto;
  gap: 4px;
  min-width: 0;
  font-size: 15px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.is-resource .activity-image {
  width: 40px;
  height: 40px;
}
.is-resource .activity-name {
  margin-bottom: 2px;
  font-size: 14px;
}
.is-resource .activity-desc {
  margin-bottom: 0;
}
@media (max-width: 560px) {
  .is-horizontal .activity-image {
    width: 64px;
    height: 64px;
  }
  .is-resource {
    flex-wrap: wrap;
  }
}
@media (prefers-reduced-motion: reduce) {
  .activity-image {
    transition: none;
  }
}
</style>
