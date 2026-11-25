<!--
  游戏社区：签到页的帐号总览。
  只做展示与跳转，不在这里改配置；凭据是否绑定直接读帐号字段，
  和签到用的凭据判定保持同一来源，避免两处口径不一致。
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CREDENTIAL_ROWS, hasCredential, type AccountInstance } from '../gameSignAccounts'

const props = defineProps<{
  accounts: readonly AccountInstance[]
  loading?: boolean
}>()

const emit = defineEmits<{ manage: [] }>()

const { t } = useI18n()

const accountRows = computed(() =>
  props.accounts.map(account => {
    const bound = CREDENTIAL_ROWS.filter(row => hasCredential(account, row.field))
    return {
      uid: account.uid,
      name: account.Name || t('core.gamesign.defaultUserName'),
      mark: (account.Name || t('core.gamesign.defaultUserName')).slice(0, 1).toUpperCase(),
      enabled: account.Enabled !== false,
      boundLabels: bound.map(row => t(row.label)),
      boundFields: new Set(bound.map(row => row.field)),
    }
  })
)

const credentialSummary = computed(() => {
  const total = props.accounts.reduce(
    (count, account) =>
      count + CREDENTIAL_ROWS.filter(row => hasCredential(account, row.field)).length,
    0
  )
  return t('core.gamesign.account.credentialCount', { n: total })
})
</script>

<template>
  <section class="account-summary">
    <div class="summary-header">
      <div class="summary-heading">
        <h3>{{ t('core.gamesign.home.accounts') }}</h3>
        <p class="summary-sub">
          {{ t('core.gamesign.account.count', { n: accounts.length }) }} ·
          {{ credentialSummary }}
        </p>
      </div>
      <a-button size="small" :disabled="loading" @click="emit('manage')">
        {{ t('core.gamesign.home.manage') }}
      </a-button>
    </div>

    <div v-if="accountRows.length > 0" class="summary-grid">
      <article v-for="row in accountRows" :key="row.uid" class="summary-card">
        <span class="summary-mark">{{ row.mark }}</span>
        <div class="summary-main">
          <div class="summary-name-line">
            <span class="summary-name">{{ row.name }}</span>
            <a-tag v-if="!row.enabled" class="summary-tag">
              {{ t('core.gamesign.account.disabledTag') }}
            </a-tag>
          </div>
          <p class="summary-detail">
            {{
              row.boundLabels.length > 0
                ? row.boundLabels.join(' · ')
                : t('core.gamesign.account.noCredential')
            }}
          </p>
        </div>
        <span class="summary-dots">
          <i
            v-for="dot in CREDENTIAL_ROWS"
            :key="dot.field"
            :class="['summary-dot', row.boundFields.has(dot.field) ? 'is-on' : '']"
            :title="t(dot.label)"
          />
        </span>
      </article>
    </div>

    <p v-else class="summary-empty">{{ t('core.gamesign.account.emptyGuide') }}</p>
  </section>
</template>

<style scoped>
.account-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.summary-heading h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: var(--ant-color-text);
}

.summary-sub {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 20px;
  color: var(--ant-color-text-secondary);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  min-width: 0;
}

.summary-mark {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.summary-main {
  flex: 1 1 auto;
  min-width: 0;
}

.summary-name-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.summary-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-tag {
  margin-inline-end: 0;
  font-size: 12px;
  line-height: 20px;
  padding: 0 4px;
}

.summary-detail {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 20px;
  color: var(--ant-color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-dots {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.summary-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-fill-secondary);
}

.summary-dot.is-on {
  background: var(--ant-color-primary);
}

.summary-empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  font-size: 14px;
  line-height: 22px;
  color: var(--ant-color-text-tertiary);
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}
</style>
