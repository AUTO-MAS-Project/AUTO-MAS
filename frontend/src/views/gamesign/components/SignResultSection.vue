<!--
  游戏社区：签到结果区。
  数据来自本体 ToolsConfig.GameSign.Result，解析后按平台分组展示，
  状态判定与账号标签共用 gameSignDisplay 的同一套规则。
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReloadOutlined } from '@ant-design/icons-vue'
import {
  getSignDetailAlias,
  getSignDetailItems,
  getSignStatusKey,
  type PlatformResult,
} from '../gameSignDisplay'

const props = defineProps<{
  result: PlatformResult
  loading?: boolean
}>()

const emit = defineEmits<{ refresh: []; sign: [] }>()

const { t } = useI18n()

const SIGNED_STATUSES = ['成功', '已签到']

interface ResultGame {
  key: string
  title: string
  status: string
  statusLabel: string
  tone: 'success' | 'warning' | 'error' | 'neutral'
  reward: string
  reason: string
}

interface ResultGroup {
  uid: string
  alias: string
  signed: number
  total: number
  games: ResultGame[]
}

interface ResultPlatform {
  name: string
  groups: ResultGroup[]
}

const platforms = computed<ResultPlatform[]>(() =>
  Object.entries(props.result).map(([name, groups]) => ({
    name,
    groups: groups.map(group => {
      const items = getSignDetailItems(group.games ?? [])
      return {
        uid: group.account_uid || group.account_alias,
        alias: getSignDetailAlias(
          group,
          group.games?.[0] ?? { game: '' },
          t('core.gamesign.unknownUser')
        ),
        signed: items.filter(item => SIGNED_STATUSES.includes(item.status)).length,
        total: items.length,
        games: items.map((item, index) => ({
          key: `${name}-${group.account_uid}-${index}`,
          title:
            item.kind === 'community'
              ? t('core.gamesign.list.kuroCoinSign')
              : item.kind === 'game'
                ? t('core.gamesign.list.gameSignTask', { game: item.game })
                : item.game,
          status: item.status,
          statusLabel: t(getSignStatusKey(item.status)),
          tone: SIGNED_STATUSES.includes(item.status)
            ? 'success'
            : item.status === '风控'
              ? 'error'
              : item.status === '失败'
                ? 'error'
                : 'neutral',
          reward: item.reward || '',
          reason: item.reason || '',
        })),
      }
    }),
  }))
)

// 逐平台账号组计数：三个状态互斥，相加即本次参与签到的账号组数量。
const summary = computed(() => {
  let signed = 0
  let failed = 0
  let risk = 0
  for (const platform of platforms.value) {
    for (const group of platform.groups) {
      if (group.total > 0 && group.signed === group.total) signed += 1
      else if (group.games.some(game => game.status === '风控')) risk += 1
      else if (group.games.some(game => game.status === '失败')) failed += 1
    }
  }
  return { signed, failed, risk }
})

const hasRecords = computed(() => platforms.value.some(platform => platform.groups.length > 0))
</script>

<template>
  <section class="sign-result">
    <div class="result-header">
      <div class="result-heading">
        <h3>{{ t('core.gamesign.result.title') }}</h3>
        <p class="result-sub">{{ t('core.gamesign.result.subtitle') }}</p>
      </div>
      <a-space :size="8">
        <a-button
          size="small"
          :loading="loading"
          :aria-label="t('core.devtools.refresh')"
          @click="emit('refresh')"
        >
          <template #icon><ReloadOutlined /></template>
          {{ t('core.devtools.refresh') }}
        </a-button>
        <a-button type="primary" size="small" :loading="loading" @click="emit('sign')">
          {{ t('core.gamesign.section.signAll') }}
        </a-button>
      </a-space>
    </div>

    <template v-if="hasRecords">
      <div class="result-summary">
        <div class="summary-cell is-success">
          <span class="summary-value">{{ summary.signed }}</span>
          <span class="summary-label">{{ t('core.gamesign.result.signed') }}</span>
        </div>
        <div class="summary-cell is-failed">
          <span class="summary-value">{{ summary.failed }}</span>
          <span class="summary-label">{{ t('core.gamesign.result.failed') }}</span>
        </div>
        <div class="summary-cell is-risk">
          <span class="summary-value">{{ summary.risk }}</span>
          <span class="summary-label">{{ t('core.gamesign.result.risk') }}</span>
        </div>
      </div>

      <div v-for="platform in platforms" :key="platform.name" class="result-platform">
        <h4 class="platform-title">
          {{ platform.name }}
          <span class="platform-count">
            {{ platform.groups.length }} {{ t('core.gamesign.result.total') }}
          </span>
        </h4>
        <div class="result-grid">
          <article v-for="group in platform.groups" :key="group.uid" class="result-card">
            <header class="result-card-head">
              <span class="result-owner">{{ group.alias }}</span>
              <a-tag
                :color="group.signed === group.total && group.total > 0 ? 'success' : 'default'"
                class="result-count-tag"
              >
                {{ group.signed }}/{{ group.total }}
                <template v-if="group.signed > 0 && group.signed < group.total">
                  · {{ t('core.gamesign.signStatus.partialFailure') }}
                </template>
              </a-tag>
            </header>
            <ul class="result-list">
              <li v-for="game in group.games" :key="game.key" class="result-row">
                <span :class="['result-dot', `is-${game.tone}`]" aria-hidden="true" />
                <span class="result-game">{{ game.title }}</span>
                <span :class="['result-status', `is-${game.tone}`]">{{ game.statusLabel }}</span>
                <span v-if="game.reward" class="result-reward">{{ game.reward }}</span>
                <span v-if="game.reason" class="result-reason">{{ game.reason }}</span>
              </li>
            </ul>
          </article>
        </div>
      </div>
    </template>

    <div v-else class="result-empty">
      <p class="result-empty-title">{{ t('core.gamesign.result.empty') }}</p>
      <p class="result-empty-desc">{{ t('core.gamesign.result.emptyGuide') }}</p>
    </div>
  </section>
</template>

<style scoped>
.sign-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.result-heading h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: var(--ant-color-text);
}

.result-sub {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-secondary);
}

.result-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.summary-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.summary-value {
  font-size: 20px;
  line-height: 28px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text);
}

.summary-cell.is-success .summary-value {
  color: var(--ant-color-success);
}

.summary-cell.is-failed .summary-value {
  color: var(--ant-color-error);
}

.summary-cell.is-risk .summary-value {
  color: var(--ant-color-warning);
}

.summary-label {
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-secondary);
}

.result-platform {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.platform-title {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.platform-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 8px;
}

.result-card {
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  min-width: 0;
}

.result-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.result-owner {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-count-tag {
  margin-inline-end: 0;
  font-variant-numeric: tabular-nums;
}

.result-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-secondary);
  flex-wrap: wrap;
}

.result-dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-fill-secondary);
  transform: translateY(-1px);
}

.result-dot.is-success {
  background: var(--ant-color-success);
}

.result-dot.is-error {
  background: var(--ant-color-error);
}

.result-dot.is-warning {
  background: var(--ant-color-warning);
}

.result-game {
  color: var(--ant-color-text);
}

.result-status.is-success {
  color: var(--ant-color-success);
}

.result-status.is-error {
  color: var(--ant-color-error);
}

.result-status.is-warning {
  color: var(--ant-color-warning);
}

.result-reward,
.result-reason {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.result-reason {
  color: var(--ant-color-text-tertiary);
}

.result-empty {
  padding: 24px 16px;
  text-align: center;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.result-empty-title {
  margin: 0;
  font-size: 14px;
  color: var(--ant-color-text);
}

.result-empty-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

@media (max-width: 860px) {
  .result-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
