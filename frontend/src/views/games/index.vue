<template>
  <AppPage layout="fill" class="emulator-page">
    <PageHeader :title="t('core.games.title')">
      <template #actions>
        <a-space size="middle">
          <a-button size="large" :loading="searching" @click="search">
            <template #icon><SearchOutlined /></template>
            {{ t('core.games.discover') }}
          </a-button>
          <a-button
            type="primary"
            size="large"
            :disabled="!api.types.value.length"
            @click="editorOpen = true"
          >
            <template #icon><PlusOutlined /></template>
            {{ t('core.games.add') }}
          </a-button>
        </a-space>
      </template>
    </PageHeader>

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
      class="games-state"
    >
      <template #empty-action>
        <a-space wrap size="middle">
          <a-button size="large" :loading="searching" @click="search">
            <template #icon><SearchOutlined /></template>
            {{ t('core.games.discover') }}
          </a-button>
          <a-button
            type="primary"
            size="large"
            :disabled="!api.types.value.length"
            @click="editorOpen = true"
          >
            <template #icon><PlusOutlined /></template>
            {{ t('core.games.add') }}
          </a-button>
        </a-space>
      </template>

      <div ref="shellHostRef" class="games-shell-host">
        <PageSurface
          :scrollable="false"
          padding="none"
          class="emulator-tabs games-shell"
          :class="{ 'games-shell--narrow': isNarrow }"
        >
          <GameTargetRail
            :rows="api.rows.value"
            :active-key="activeKey"
            :operations-by-target="operationsByTarget"
            :narrow="isNarrow"
            @select="selectTarget"
          />
          <GameTargetPanel
            v-if="activeRow"
            :key="activeRow.uid"
            :game="activeRow"
            :active-operations="activeRowOperations"
            :narrow="isNarrow"
            @cancel="cancel"
            @dirty-change="setEditorDirty"
          />
        </PageSurface>
      </div>
    </StateView>

    <GameEditor
      v-if="editorOpen"
      :open="true"
      :types="api.types.value"
      @created="uid => void selectTarget(uid)"
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
        <template #emptyText>
          <NoData :description="t('core.games.noDiscovery')" size="sm" />
        </template>
      </a-list>
    </AppModal>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { AppModal, AppPage, NoData, PageHeader, PageSurface, StateView } from '@/components/ui'
import type { ActiveTriggerField } from '@/api'
import { useGamesApi } from '@/composables/useGamesApi'
import { useGameTriggers } from '@/composables/useGameTriggers'
import { useActiveTriggers } from '@/composables/useActiveTriggers'
import { useConfirm } from '@/composables/useConfirm'
import { buildTargetOperationsMap } from './gamePresentation'
import GameEditor from './components/GameEditor.vue'
import GameTargetPanel from './components/GameTargetPanel.vue'
import GameTargetRail from './components/GameTargetRail.vue'

/** 低于此内容宽度（对应主窗口约 1144px）时左栏自动收起为顶部切换栏。 */
const NARROW_LAYOUT_BREAKPOINT = 920

const { t } = useI18n()
const { confirm } = useConfirm()
const api = useGamesApi()
const operations = useGameTriggers()
const { data: activeTriggers } = useActiveTriggers()
const activeKey = ref<string>()
const dirtyTargetUid = ref<string | null>(null)
const switchingTarget = ref(false)
const editorOpen = ref(false)
const searching = ref(false)
const foundOpen = ref(false)
const importing = ref('')
const found = ref<{ uid: string; name: string; path: string }[]>([])
const shellHostRef = ref<HTMLElement | null>(null)
const isNarrow = ref(false)

let resizeObserver: ResizeObserver | null = null

watch(shellHostRef, host => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (!host) return
  const updateWidth = (width: number) => {
    if (width > 0) isNarrow.value = width < NARROW_LAYOUT_BREAKPOINT
  }
  updateWidth(host.clientWidth)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect.width ?? host.clientWidth
      updateWidth(width)
    })
    resizeObserver.observe(host)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

const operationsByTarget = computed(() =>
  buildTargetOperationsMap(api.rows.value, activeTriggers.value)
)

const activeRow = computed(() => api.rows.value.find(row => row.uid === activeKey.value))
const isActiveEditorDirty = computed(() =>
  Boolean(activeKey.value && dirtyTargetUid.value === activeKey.value)
)

function setEditorDirty(uid: string, dirty: boolean): void {
  if (dirty) {
    dirtyTargetUid.value = uid
  } else if (dirtyTargetUid.value === uid) {
    dirtyTargetUid.value = null
  }
}

async function selectTarget(uid: string): Promise<void> {
  if (!uid || uid === activeKey.value || switchingTarget.value) return
  if (isActiveEditorDirty.value) {
    switchingTarget.value = true
    try {
      const confirmed = await confirm({
        tone: 'warning',
        title: t('core.games.discard'),
      })
      if (!confirmed) return
    } finally {
      switchingTarget.value = false
    }
  }
  if (!api.rows.value.some(row => row.uid === uid)) return
  dirtyTargetUid.value = null
  activeKey.value = uid
}

const activeRowOperations = computed(() =>
  activeRow.value ? (operationsByTarget.value.get(activeRow.value.uid) ?? []) : []
)

const allActiveOperationKey = computed(() =>
  Array.from(operationsByTarget.value.values())
    .flatMap(items => items.map(item => item.taskId))
    .sort()
    .join(',')
)

watch(allActiveOperationKey, () => void api.refresh())

watch(
  api.rows,
  rows => {
    if (dirtyTargetUid.value && !rows.some(row => row.uid === dirtyTargetUid.value)) {
      dirtyTargetUid.value = null
    }
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
    const createdUid = response.order?.[0]?.uid
    if (createdUid && !isActiveEditorDirty.value) activeKey.value = createdUid
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

.games-state {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.games-shell-host {
  flex: 1;
  min-height: 0;
  display: flex;
}

.games-shell {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  overflow: hidden;
}

.games-shell--narrow {
  display: flex;
  flex-direction: column;
}
</style>
