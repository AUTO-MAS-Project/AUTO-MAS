<template>
  <main class="emulator-page">
    <header class="app-page-header">
      <h1 class="app-page-title">{{ t('core.games.title') }}</h1>
    </header>

    <a-alert v-if="api.error.value" type="error" :message="String(api.error.value)" show-icon>
      <template #action
        ><a-button @click="api.prepare">{{ t('core.games.retry') }}</a-button></template
      >
    </a-alert>

    <a-spin :spinning="api.loading.value" class="page-content">
      <div v-if="!api.rows.value.length && !api.loading.value" class="empty-state-large">
        <a-empty :description="t('core.games.empty')" />
        <a-space wrap>
          <a-button :loading="searching" @click="search">
            <template #icon><SearchOutlined /></template>
            {{ t('core.games.discover') }}
          </a-button>
          <a-button type="primary" :disabled="!api.types.value.length" @click="editorOpen = true">
            <template #icon><PlusOutlined /></template>
            {{ t('core.games.add') }}
          </a-button>
        </a-space>
      </div>
      <a-tabs
        v-else-if="api.rows.value.length"
        v-model:active-key="activeKey"
        type="editable-card"
        hide-add
        class="emulator-tabs app-page-surface app-page-surface--tabs"
      >
        <a-tab-pane v-for="row in api.rows.value" :key="row.uid" :closable="false">
          <template #tab>
            <span class="tab-title" :title="row.document.info?.name ?? undefined">
              {{ row.document.info?.name || t('core.emulator.unnamed') }}
            </span>
          </template>
          <GameTargetPanel :game="row" />
        </a-tab-pane>
        <template #rightExtra>
          <a-space wrap class="tab-extra-actions">
            <a-button :loading="searching" @click="search">
              <template #icon><SearchOutlined /></template>
              {{ t('core.games.discover') }}
            </a-button>
            <a-button type="primary" :disabled="!api.types.value.length" @click="editorOpen = true">
              <template #icon><PlusOutlined /></template>
              {{ t('core.games.add') }}
            </a-button>
          </a-space>
        </template>
      </a-tabs>
    </a-spin>

    <GameEditor
      v-if="editorOpen"
      :open="true"
      :types="api.types.value"
      @created="uid => (activeKey = uid)"
      @close="editorOpen = false"
    />
    <AppModal
      :open="foundOpen"
      size="md"
      :title="t('core.games.discoveryResults')"
      footer="none"
      @cancel="foundOpen = false"
    >
      <a-list :data-source="found">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta :title="item.name" :description="item.path" />
            <a-button :loading="importing === item.uid" @click="importFound(item.uid)">
              {{ t('core.games.import') }}
            </a-button>
          </a-list-item>
        </template>
        <template #emptyText><a-empty :description="t('core.games.noDiscovery')" /></template>
      </a-list>
    </AppModal>
    <a-alert
      v-for="item in activeOperations"
      :key="item.taskId"
      type="info"
      show-icon
      class="operation-alert"
      :message="t('core.games.operationRunning')"
    >
      <template #action>
        <a-button size="small" :loading="item.cancelling" @click="cancel(item)">
          {{ t('core.games.cancel') }}
        </a-button>
      </template>
    </a-alert>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { AppModal } from '@/components/ui'
import type { ActiveTriggerField } from '@/api'
import { gameDevices } from '@/types/games'
import { useGamesApi } from '@/composables/useGamesApi'
import { useGameTriggers } from '@/composables/useGameTriggers'
import { useActiveTriggers } from '@/composables/useActiveTriggers'
import GameEditor from './components/GameEditor.vue'
import GameTargetPanel from './components/GameTargetPanel.vue'

const { t } = useI18n()
const api = useGamesApi()
const operations = useGameTriggers()
const { data: activeTriggers } = useActiveTriggers()
const activeKey = ref<string>()
const editorOpen = ref(false)
const searching = ref(false)
const foundOpen = ref(false)
const importing = ref('')
const found = ref<{ uid: string; name: string; path: string }[]>([])
const activeOperations = computed(() => {
  const targets = new Set(
    api.rows.value.flatMap(row => [row.uid, ...gameDevices(row).map(device => device.uid)])
  )
  return (activeTriggers.value ?? []).filter(item => targets.has(item.configUid))
})
watch(
  () =>
    activeOperations.value
      .map(item => item.taskId)
      .sort()
      .join(','),
  () => void api.refresh()
)

watch(
  api.rows,
  rows => {
    if (!rows.some(row => row.uid === activeKey.value)) activeKey.value = rows[0]?.uid
  },
  { immediate: true }
)

async function search() {
  searching.value = true
  try {
    const response = await api.search()
    found.value = Object.entries(response.data ?? {}).map(([uid, item]) => ({
      uid,
      name: typeof item.name === 'string' ? item.name : '',
      path: typeof item.path === 'string' ? item.path : '',
    }))
    foundOpen.value = true
  } catch (error) {
    message.error(String(error))
  } finally {
    searching.value = false
  }
}

async function importFound(uid: string) {
  importing.value = uid
  try {
    const response = await api.importFound(uid)
    activeKey.value = response.order?.[0]?.uid ?? activeKey.value
    found.value = found.value.filter(item => item.uid !== uid)
    if (!found.value.length) foundOpen.value = false
  } catch (error) {
    message.error(String(error))
  } finally {
    importing.value = ''
  }
}

async function cancel(field: ActiveTriggerField) {
  try {
    await operations.cancel(field)
  } catch (error) {
    message.error(String(error))
  }
}
</script>

<style scoped>
.emulator-page {
  min-height: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.page-content {
  flex: 1;
  min-height: 0;
}

.empty-state-large {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.emulator-tabs :deep(.ant-tabs-nav) {
  margin-bottom: var(--app-page-content-gap);
}

.tab-title {
  font-weight: 500;
}

.tab-extra-actions {
  margin-inline-start: 8px;
}

.operation-alert {
  margin-top: 12px;
}
</style>
