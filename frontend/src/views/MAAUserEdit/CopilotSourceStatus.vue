<template>
  <div class="source-status">
    <div class="source-panel" :class="{ 'source-panel-compact': compact }">
      <DatabaseOutlined aria-hidden="true" class="source-icon" />
      <div class="source-content">
        <div class="source-title">
          <strong>{{
            state?.available
              ? t('maaCopilot.cached', { count: state.count })
              : t('maaCopilot.noData')
          }}</strong>
          <span v-if="state?.available" class="source-origin">
            {{ t(`maaCopilot.origins.${state.dataSource ?? 'unknown'}`) }}
          </span>
        </div>
        <dl v-if="state?.available" class="source-dates">
          <div>
            <dt>{{ t('maaCopilot.generatedAt') }}</dt>
            <dd>{{ sourceTime }}</dd>
          </div>
          <div>
            <dt>{{ t('maaCopilot.downloadedAt') }}</dt>
            <dd>{{ formatTime(state.downloadedAt) }}</dd>
          </div>
        </dl>
        <div v-if="source === 'all'" class="source-note">
          <span>{{
            t(
              state?.dataSource === 'copilot'
                ? 'maaCopilot.liveHint'
                : 'maaCopilot.snapshotSchedule'
            )
          }}</span>
          <a-popover :title="t('maaCopilot.dataSource')" trigger="click" placement="bottomLeft">
            <template #content
              ><p class="source-detail">{{ t('maaCopilot.snapshotHint') }}</p></template
            >
            <a-button type="link" size="small"
              >{{ t('maaCopilot.sourceDetails') }}<InfoCircleOutlined aria-hidden="true"
            /></a-button>
          </a-popover>
        </div>
      </div>
      <div v-if="!compact" class="source-actions">
        <a-button
          size="small"
          :loading="state?.running"
          :disabled="disabled"
          @click="emit('sync', false)"
        >
          <template #icon><CloudDownloadOutlined aria-hidden="true" /></template>
          {{ t('maaCopilot.load') }}
        </a-button>
        <a-tooltip :title="t('maaCopilot.refreshHint')">
          <a-button
            type="link"
            size="small"
            :disabled="disabled || state?.running"
            @click="emit('sync', true)"
          >
            {{ t('maaCopilot.refresh') }}
          </a-button>
        </a-tooltip>
      </div>
    </div>
    <div v-if="state?.running" class="sync-progress">
      <a-progress :percent="syncPercent" :show-info="false" />
      {{ t('maaCopilot.syncing', { loaded: state.loaded, total: state.total || '…' }) }}
    </div>
    <a-alert v-if="state?.error" :message="state.error" type="warning" show-icon />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'
import { CloudDownloadOutlined, DatabaseOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import type { MaaCopilotSourceIn, MaaCopilotSourceOut } from '@/api'

const props = defineProps<{
  state: MaaCopilotSourceOut | null
  source: NonNullable<MaaCopilotSourceIn['source']>
  compact: boolean
  disabled: boolean
}>()
const emit = defineEmits<{ sync: [refresh: boolean] }>()
const { t } = useI18n()
const formatTime = (value?: number) =>
  value ? dayjs.unix(value).format('YYYY-MM-DD HH:mm:ss') : '—'
const sourceTime = computed(() => formatTime(props.state?.updatedAt))
const syncPercent = computed(() =>
  props.state?.total
    ? Math.min(100, Math.round(((props.state.loaded ?? 0) / props.state.total) * 100))
    : 0
)
</script>

<style scoped>
@media (max-width: 1100px) {
  .source-panel {
    flex-wrap: wrap;
  }
  .source-actions {
    flex-direction: row;
    flex-wrap: wrap;
    width: 100%;
    padding-left: 32px;
  }
}
.source-panel {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}
.source-icon {
  margin-top: 3px;
  color: var(--ant-color-text-tertiary);
  font-size: 20px;
}
.source-panel-compact {
  padding: 12px 16px;
}
.source-content {
  flex: 1;
  min-width: 0;
}
.source-title {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-bottom: 8px;
}
.source-title strong {
  font-weight: 600;
}
.source-origin,
.source-note,
.source-dates {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.source-dates {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 24px;
  margin: 0 0 4px;
}
.source-dates > div {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
}
.source-dates dd {
  margin: 0;
  color: var(--ant-color-text);
  font-variant-numeric: tabular-nums;
}
.source-note {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.source-note .ant-btn {
  font-size: 12px;
}
.source-detail {
  max-width: 360px;
  margin: 0;
  line-height: 1.7;
}
.source-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.sync-progress {
  margin-top: 16px;
}
</style>
