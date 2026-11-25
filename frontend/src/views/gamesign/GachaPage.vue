<!--
  游戏社区：抽卡记录页。
  首批只接森空岛明日方舟：卡池与角色都要从森空岛令牌走鹰角接口读，
  角色 UID 无法从便笺结果里稳定取到，所以由用户手填。
  读取动作只在用户点「获取记录」时触发一次，插件端不排定时任务。
-->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { NoData, StatusChip } from '@/components/ui'
import type { AccountInstance } from './gameSignAccounts'
import { formatRecordTime, useGachaRecords } from './useGachaRecords'

const props = defineProps<{
  /** 帐号组清单：抽卡读取用的是账号组里的森空岛凭据 */
  accounts: readonly AccountInstance[]
  disabled?: boolean
}>()

const emit = defineEmits<{ manage: [] }>()

const { t } = useI18n()

const {
  records,
  pools,
  games,
  loadGames,
  total,
  page,
  pageSize,
  querying,
  fetching,
  errorMessage,
  unavailable,
  query,
  fetchRecords,
  reset,
} = useGachaRecords()

const game = ref('arknights')
const accountUid = ref('')
const playerUid = ref('')
const pool = ref('')

/**
 * 已知游戏标识 → 词条键。
 *
 * 不能拼 `t(\`...${value}\`)`：插件以后接通新游戏时，词表里没有对应键，
 * 拼出来的 key 会被 vue-i18n 原样渲染成「core.gamesign.gacha.gameNames.xxx」。
 * 未收录的标识回退显示插件给的原始值，至少不会露出内部键名。
 */
const GAME_LABEL_KEYS: Record<string, string> = {
  arknights: 'core.gamesign.gacha.gameNames.arknights',
}

const gameLabel = (value: string) => {
  const key = GAME_LABEL_KEYS[value]
  return key ? t(key) : value
}

/** 清单拿不到（插件未启用）时也要能显示当前游戏的中文名，否则下拉里会露出原始 id */
const gameOptions = computed(() =>
  (games.value.length ? games.value : [game.value]).map(value => ({
    value,
    label: gameLabel(value),
  }))
)

/** 只在有森空岛凭据的账号组里选：其余账号抽卡接口必然报「请先登录森空岛」 */
const accountOptions = computed(() =>
  props.accounts
    .filter(account => account.SklandToken.trim().length > 0)
    .map(account => ({ value: account.uid, label: account.Name }))
)

const hasSklandAccount = computed(() => accountOptions.value.length > 0)

const poolOptions = computed(() => [
  { value: '', label: t('core.gamesign.gacha.poolAll') },
  ...pools.value.map(item => ({ value: item.poolType, label: item.poolName })),
])

const canQuery = computed(
  () =>
    !props.disabled && !unavailable.value && !querying.value && playerUid.value.trim().length > 0
)

const canFetch = computed(
  () =>
    !props.disabled &&
    !unavailable.value &&
    !fetching.value &&
    !!accountUid.value &&
    playerUid.value.trim().length > 0
)

const rarityTone = (rarity: number): 'warning' | 'success' | 'processing' | 'neutral' => {
  if (rarity >= 6) return 'warning'
  if (rarity === 5) return 'success'
  if (rarity === 4) return 'processing'
  return 'neutral'
}

const columns = computed(() => [
  { title: t('core.gamesign.gacha.columnTime'), key: 'time', dataIndex: 'time', width: 180 },
  { title: t('core.gamesign.gacha.columnPool'), key: 'poolName', dataIndex: 'poolName' },
  { title: t('core.gamesign.gacha.columnName'), key: 'name', dataIndex: 'name' },
  { title: t('core.gamesign.gacha.columnRarity'), key: 'rarity', dataIndex: 'rarity', width: 96 },
])

const pagination = computed(() => ({
  current: page.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: false,
  size: 'small' as const,
}))

const runQuery = async () => {
  if (!playerUid.value.trim()) {
    message.warning(t('core.gamesign.gacha.needPlayerUid'))
    return
  }
  await query({ game: game.value, playerUid: playerUid.value.trim(), pool: pool.value })
}

const runFetch = async () => {
  if (!accountUid.value || !playerUid.value.trim()) {
    message.warning(t('core.gamesign.gacha.needPlayerUid'))
    return
  }
  await fetchRecords({
    game: game.value,
    accountUid: accountUid.value,
    playerUid: playerUid.value.trim(),
  })
}

/** 卡池切换即重新查询：卡池筛选只影响后端查询条件，不影响已入库数据 */
const selectPool = (value: string) => {
  if (pool.value === value) return
  pool.value = value
  page.value = 1
  void runQuery()
}

const handlePageChange = (next: { current?: number }) => {
  page.value = next.current && next.current > 0 ? next.current : 1
  void runQuery()
}

/** 换角色或换帐号时上一份记录不再属于当前筛选，先清空再等用户查询 */
const handleTargetChange = () => {
  reset()
  pool.value = ''
}

watch([accountUid, playerUid], handleTargetChange)

/**
 * 帐号列表由父级异步加载：首屏挂载时还没到，等清单到位再补默认选中，
 * 否则「获取记录」会因为没选帐号一直点不动。
 */
watch(accountOptions, options => {
  if (!accountUid.value && options.length) accountUid.value = options[0].value
})

onMounted(async () => {
  // 探测同时带出游戏清单；插件未启用时由 composable 给出提示，页面只需禁用筛选
  await loadGames()
  if (games.value.length && !games.value.includes(game.value)) {
    game.value = games.value[0]
  }
})
</script>

<template>
  <div class="gacha-page">
    <header class="gacha-header">
      <div class="gacha-heading">
        <h3 class="gacha-title">{{ t('core.gamesign.gacha.title') }}</h3>
        <p class="gacha-sub">{{ t('core.gamesign.gacha.description') }}</p>
      </div>
    </header>

    <a-alert
      v-if="unavailable !== ''"
      class="gacha-alert"
      type="info"
      show-icon
      :message="unavailable"
      :description="t('core.gamesign.gacha.pluginMissingDesc')"
    />
    <a-alert
      v-else-if="!hasSklandAccount"
      class="gacha-alert"
      type="warning"
      show-icon
      :message="t('core.gamesign.gacha.noAccount')"
      :description="t('core.gamesign.gacha.noAccountDesc')"
    >
      <template #action>
        <a-button size="small" @click="emit('manage')">
          {{ t('core.gamesign.home.manage') }}
        </a-button>
      </template>
    </a-alert>

    <!-- 用 aria-labelledby 关联标签：a-select 不是 label 可绑定的原生控件，包在 label 里点了也不会聚焦 -->
    <section class="gacha-filter">
      <div class="filter-item">
        <span id="gacha-filter-game" class="filter-label">
          {{ t('core.gamesign.gacha.gameLabel') }}
        </span>
        <a-select
          v-model:value="game"
          class="filter-control"
          aria-labelledby="gacha-filter-game"
          :options="gameOptions"
          :disabled="unavailable !== '' || games.length === 0"
        />
      </div>
      <div class="filter-item">
        <span id="gacha-filter-account" class="filter-label">
          {{ t('core.gamesign.gacha.account') }}
        </span>
        <a-select
          v-model:value="accountUid"
          class="filter-control"
          aria-labelledby="gacha-filter-account"
          :options="accountOptions"
          :disabled="unavailable !== '' || !hasSklandAccount"
          :placeholder="t('core.gamesign.gacha.selectAccount')"
        />
      </div>
      <div class="filter-item">
        <span id="gacha-filter-uid" class="filter-label">
          {{ t('core.gamesign.gacha.playerUid') }}
        </span>
        <a-input
          v-model:value="playerUid"
          class="filter-control"
          aria-labelledby="gacha-filter-uid"
          allow-clear
          :disabled="unavailable !== ''"
          :placeholder="t('core.gamesign.gacha.playerUidPlaceholder')"
        />
      </div>
      <div class="filter-actions">
        <a-button :disabled="!canQuery" :loading="querying" @click="runQuery">
          <template #icon><SearchOutlined /></template>
          {{ t('core.gamesign.gacha.query') }}
        </a-button>
        <a-button type="primary" :disabled="!canFetch" :loading="fetching" @click="runFetch">
          <template #icon><ReloadOutlined /></template>
          {{ t('core.gamesign.gacha.fetch') }}
        </a-button>
      </div>
    </section>

    <a-alert
      v-if="errorMessage"
      class="gacha-alert"
      type="error"
      show-icon
      :message="errorMessage"
    />

    <section v-if="pools.length" class="gacha-pools">
      <span id="gacha-pools-hint" class="pool-hint">
        {{ t('core.gamesign.gacha.poolsTitle') }}
      </span>
      <div class="pool-chips" role="toolbar" aria-labelledby="gacha-pools-hint">
        <button
          v-for="item in poolOptions"
          :key="item.value || 'all'"
          type="button"
          :class="['pool-chip', pool === item.value ? 'is-active' : '']"
          :aria-pressed="pool === item.value"
          @click="selectPool(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
    </section>

    <a-table
      class="gacha-table"
      :columns="columns"
      :data-source="records"
      :pagination="pagination"
      :loading="querying"
      row-key="id"
      size="middle"
      :scroll="{ x: 'max-content' }"
      @change="handlePageChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'time'">
          <span class="cell-time">{{ formatRecordTime(record.time) }}</span>
        </template>
        <template v-else-if="column.key === 'poolName'">
          <span class="cell-pool">{{ record.poolName || '-' }}</span>
        </template>
        <template v-else-if="column.key === 'name'">
          <span class="cell-name">{{ record.name }}</span>
          <StatusChip v-if="record.isFree" tone="neutral">{{
            t('core.gamesign.gacha.free')
          }}</StatusChip>
        </template>
        <template v-else-if="column.key === 'rarity'">
          <StatusChip :tone="rarityTone(record.rarity)">★{{ record.rarity }}</StatusChip>
        </template>
      </template>
    </a-table>

    <NoData
      v-if="!querying && records.length === 0 && unavailable === ''"
      class="gacha-empty"
      :description="t('core.gamesign.gacha.emptyGuide')"
    />
  </div>
</template>

<style scoped>
.gacha-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 24px 24px;
}

.gacha-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gacha-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: var(--ant-color-text);
}

.gacha-sub {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--ant-color-text-secondary);
}

.gacha-alert {
  margin: 0;
}

.gacha-filter {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  align-items: end;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.filter-label {
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
  color: var(--ant-color-text-secondary);
}

.filter-control {
  width: 100%;
}

.filter-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.gacha-pools {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 12px;
}

.pool-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pool-hint {
  font-size: 12px;
  line-height: 20px;
  color: var(--ant-color-text-tertiary);
}

.pool-chip {
  padding: 4px 10px;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-quaternary);
  border: 0;
  border-radius: 999px;
  cursor: pointer;
}

.pool-chip.is-active {
  color: var(--ant-color-text);
  font-weight: 600;
  background: var(--ant-color-fill-secondary);
  box-shadow: inset 0 -2px var(--ant-color-primary);
}

.cell-time {
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text-secondary);
}

.cell-pool {
  color: var(--ant-color-text-secondary);
}

.cell-name {
  margin-right: 6px;
  color: var(--ant-color-text);
}

.gacha-table {
  min-width: 0;
}

.gacha-empty {
  padding: 24px 0;
}

@media (max-width: 860px) {
  .gacha-page {
    padding: 12px 16px 16px;
  }

  .filter-actions {
    justify-content: stretch;
  }
}
</style>
