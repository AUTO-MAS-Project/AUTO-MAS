<!--
  游戏社区：帐号管理页。
  每个帐号一张卡片，凭据逐项绑定，编辑在右侧抽屉完成；
  排序沿用原来的拖拽交互，保存失败会重新拉取服务端顺序。
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import { PlusOutlined } from '@ant-design/icons-vue'
import { useConfirm } from '@/composables/useConfirm'
import AccountCard from './components/AccountCard.vue'
import AccountEditorDrawer from './components/AccountEditorDrawer.vue'
import { useGameSignAccounts } from './useGameSignAccounts'
import type { AccountInstance } from './gameSignAccounts'

const props = defineProps<{
  resultSource: () => string | null | undefined
}>()

const { t } = useI18n()
const { confirm } = useConfirm()

const {
  accounts,
  loading,
  reordering,
  load,
  createAccount,
  saveAccount,
  removeAccount,
  toggleEnabled,
  reorder,
  reloadAccount,
} = useGameSignAccounts(() => props.resultSource())

const drawerVisible = ref(false)
const editingAccount = ref<AccountInstance | null>(null)
const adding = ref(false)
const saving = ref(false)

const accountCount = computed(() => accounts.value.length)

const openDrawer = (account: AccountInstance) => {
  editingAccount.value = account
  drawerVisible.value = true
}

const closeDrawer = () => {
  drawerVisible.value = false
  editingAccount.value = null
}

const handleAdd = async () => {
  adding.value = true
  try {
    const created = await createAccount()
    if (created) openDrawer(created)
  } finally {
    adding.value = false
  }
}

const handleSave = async (account: AccountInstance, patch: Record<string, unknown>) => {
  if (!patch || Object.keys(patch).length === 0) {
    closeDrawer()
    return
  }
  saving.value = true
  try {
    const saved = await saveAccount(account, patch)
    if (saved) {
      closeDrawer()
      // 名称等字段可能已被后端规范化，重新拉一次保证展示与后端一致
      await load()
    }
  } finally {
    saving.value = false
  }
}

const handleRemove = async (account: AccountInstance) => {
  const confirmed = await confirm({
    tone: 'danger',
    title: t('core.gamesign.toast.deleteTitle'),
    description: t('core.gamesign.toast.deleteContent', {
      name: account.Name || t('core.gamesign.defaultUserName'),
    }),
    okText: t('core.gamesign.list.del'),
  })
  if (!confirmed) return
  await removeAccount(account)
}

const handleToggle = (account: AccountInstance, enabled: boolean) => {
  void toggleEnabled(account, enabled)
}

/**
 * 拖拽松手后 vuedraggable 只抛出新数组，不会自己写回源数据。
 *
 * 这里接住它给出的顺序再提交：只监听 @end 的话拿不到新顺序，
 * 提交的仍是拖动前的旧顺序，刷新后又回到原位。
 */
const handleReorder = (next: AccountInstance[]) => {
  void reorder(next.map(item => item.uid))
}

// 帐号列表是模块级共享状态，这里拉一次保证直连帐号页时也有最新快照
onMounted(() => {
  void load()
})
</script>

<template>
  <div class="accounts-page">
    <div class="accounts-header">
      <div class="accounts-heading">
        <h3>{{ t('core.gamesign.account.title') }}</h3>
        <p class="accounts-sub">{{ t('core.gamesign.account.subtitle') }}</p>
      </div>
      <a-button type="primary" :loading="adding" @click="handleAdd">
        <template #icon><PlusOutlined /></template>
        {{ t('core.gamesign.list.add') }}
      </a-button>
    </div>

    <a-spin :spinning="loading && accountCount === 0">
      <draggable
        v-if="accountCount > 0"
        :model-value="accounts"
        item-key="uid"
        :animation="200"
        :disabled="reordering"
        handle=".card-mark"
        ghost-class="account-ghost"
        class="accounts-grid"
        @update:model-value="handleReorder"
      >
        <template #item="{ element }">
          <AccountCard
            :account="element"
            :disabled="reordering"
            @toggle="handleToggle(element, $event)"
            @edit="openDrawer(element)"
            @remove="handleRemove(element)"
          />
        </template>
      </draggable>

      <div v-else-if="!loading" class="accounts-empty">
        <a-empty :description="t('core.gamesign.list.empty')">
          <template #description>
            <p class="empty-title">{{ t('core.gamesign.list.empty') }}</p>
            <p class="empty-guide">{{ t('core.gamesign.list.emptyGuide') }}</p>
          </template>
        </a-empty>
      </div>
    </a-spin>

    <AccountEditorDrawer
      :open="drawerVisible"
      :account="editingAccount"
      :saving="saving"
      :on-reload="reloadAccount"
      @close="closeDrawer"
      @save="handleSave"
    />
  </div>
</template>

<style scoped>
.accounts-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 24px 24px;
}

.accounts-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.accounts-heading h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: var(--ant-color-text);
}

.accounts-sub {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-tertiary);
}

.accounts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.account-ghost {
  opacity: 0.4;
}

.accounts-empty {
  padding: 40px 0;
}

.empty-title {
  margin: 0;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.empty-guide {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

@media (max-width: 860px) {
  .accounts-page {
    padding: 12px 16px 16px;
  }

  .accounts-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
