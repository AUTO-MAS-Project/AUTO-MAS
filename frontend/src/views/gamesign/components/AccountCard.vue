<!--
  游戏社区：帐号管理页的单张帐号卡片。
  卡片只负责展示与发出意图（切换启用、编辑、移除），状态与提交由父级统一处理，
  这样列表刷新、失败回滚都留在同一处。
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import {
  CREDENTIAL_ROWS,
  credentialCount,
  hasCredential,
  toAccountForm,
  type AccountInstance,
} from '../gameSignAccounts'

const props = defineProps<{
  account: AccountInstance
  disabled?: boolean
}>()

const emit = defineEmits<{
  toggle: [enabled: boolean]
  edit: []
  remove: []
}>()

const { t } = useI18n()

const form = computed(() => toAccountForm(props.account))
const displayName = computed(() => props.account.Name || t('core.gamesign.defaultUserName'))
const mark = computed(() => displayName.value.slice(0, 1).toUpperCase())
const boundCount = computed(() => credentialCount(form.value))
const rows = computed(() =>
  CREDENTIAL_ROWS.map(row => ({
    field: row.field,
    label: t(row.label),
    bound: hasCredential(form.value, row.field),
  }))
)
</script>

<template>
  <article class="account-card">
    <header class="card-head">
      <span class="card-mark" :title="t('core.gamesign.list.drag')">{{ mark }}</span>
      <div class="card-head-main">
        <div class="card-name-line">
          <span class="card-name">{{ displayName }}</span>
          <a-tag v-if="account.Enabled === false" class="card-tag">
            {{ t('core.gamesign.account.disabledTag') }}
          </a-tag>
        </div>
        <p class="card-meta">
          {{
            boundCount > 0
              ? t('core.gamesign.account.credentialCount', { n: boundCount })
              : t('core.gamesign.account.noCredential')
          }}
        </p>
      </div>
      <a-switch
        size="small"
        :checked="account.Enabled !== false"
        :disabled="disabled"
        :aria-label="t('core.gamesign.account.enabled')"
        @change="emit('toggle', Boolean($event))"
      />
    </header>

    <ul class="cred-list">
      <li v-for="row in rows" :key="row.field" class="cred-row">
        <span class="cred-label">{{ row.label }}</span>
        <span :class="['cred-value', row.bound ? 'is-bound' : '']">
          {{ row.bound ? t('core.gamesign.account.bound') : t('core.gamesign.account.unbound') }}
        </span>
        <a-button
          type="link"
          size="small"
          class="cred-action"
          :disabled="disabled"
          @click="emit('edit')"
        >
          {{ t('core.gamesign.account.edit') }}
        </a-button>
      </li>
    </ul>

    <footer class="card-foot">
      <span class="card-local">{{ t('core.gamesign.account.localOnly') }}</span>
      <a-space :size="4">
        <a-button type="text" size="small" :disabled="disabled" @click="emit('edit')">
          <template #icon><EditOutlined /></template>
          {{ t('core.gamesign.list.edit') }}
        </a-button>
        <a-button type="text" danger size="small" :disabled="disabled" @click="emit('remove')">
          <template #icon><DeleteOutlined /></template>
          {{ t('core.gamesign.account.remove') }}
        </a-button>
      </a-space>
    </footer>
  </article>
</template>

<style scoped>
.account-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg);
  background: var(--app-appearance-surface-bg, var(--ant-color-bg-container));
  min-width: 0;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-mark {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.card-head-main {
  flex: 1 1 auto;
  min-width: 0;
}

.card-name-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-tag {
  margin-inline-end: 0;
  font-size: 11px;
  line-height: 16px;
  padding: 0 4px;
}

.card-meta {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-tertiary);
}

.cred-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
}

.cred-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.cred-label {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cred-value {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.cred-value.is-bound {
  color: var(--ant-color-success);
}

.cred-action {
  padding: 0 4px;
  height: 22px;
  font-size: 12px;
}

.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.card-local {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
