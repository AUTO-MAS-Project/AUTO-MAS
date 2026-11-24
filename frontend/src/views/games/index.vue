<template>
  <AppPage layout="scroll" class="emulator-page">
    <PageHeader :title="t('core.games.title')" />

    <ApiRetryAlert
      :error="api.error.value ? String(api.error.value) : null"
      :loading="api.loading.value"
      class="games-error"
      @retry="api.prepare"
    />

    <StateView
      :loading="api.loading.value"
      :empty="!api.rows.value.length"
      :empty-description="t('core.games.empty')"
      empty-size="lg"
      :min-height="320"
      overlay-loading
    >
      <template #empty-action>
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
      </template>

      <PageSurface :scrollable="false" class="emulator-tabs">
        <a-tabs v-model:active-key="activeKey" type="editable-card" hide-add>
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
              <a-button
                type="primary"
                :disabled="!api.types.value.length"
                @click="editorOpen = true"
              >
                <template #icon><PlusOutlined /></template>
                {{ t('core.games.add') }}
              </a-button>
            </a-space>
          </template>
        </a-tabs>
      </PageSurface>
    </StateView>

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
        <template #emptyText
          ><NoData :description="t('core.games.noDiscovery')" size="sm"
        /></template>
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
  </AppPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { AppModal, AppPage, NoData, PageHeader, PageSurface, StateView } from '@/components/ui'
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
.games-error {
  margin-bottom: 12px;
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
