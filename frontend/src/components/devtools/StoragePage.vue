<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CopyOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { confirmDevtoolsAction, copyDevtoolsText, formatBytes, readStorageEntries } from './helpers'
import type { StorageEntry } from './types'

const { t } = useI18n()
const scope = ref('local')
const search = ref('')
const entries = ref<StorageEntry[]>([])
const error = ref('')
const selectedKey = ref<string | null>(null)
const creating = ref(false)
const editorKey = ref('')
const editorValue = ref('')
const originalValue = ref('')
const saving = ref(false)
const selectedRowKeys = computed(() => (selectedKey.value === null ? [] : [selectedKey.value]))
const hasEditor = computed(() => creating.value || selectedKey.value !== null)
const dirty = computed(() =>
  creating.value
    ? !!editorKey.value || !!editorValue.value
    : selectedKey.value !== null && editorValue.value !== originalValue.value
)
const filteredEntries = computed(() => {
  const query = search.value.toLowerCase()
  return entries.value.filter(
    entry => entry.key.toLowerCase().includes(query) || entry.value.toLowerCase().includes(query)
  )
})
const totalSize = computed(() =>
  formatBytes(entries.value.reduce((total, entry) => total + entry.bytes, 0))
)
const columns = computed(() => [
  { title: t('core.devtools.storageKey'), dataIndex: 'key', key: 'key' },
  { title: t('core.devtools.type'), dataIndex: 'type', key: 'type', width: 84 },
])
const scopeOptions = [
  { label: 'localStorage', value: 'local' },
  { label: 'sessionStorage', value: 'session' },
]
const currentStorage = () => (scope.value === 'local' ? window.localStorage : window.sessionStorage)
let leaveConfirmation: Promise<boolean> | null = null

const canLeave = (): Promise<boolean> => {
  if (saving.value) return Promise.resolve(false)
  if (!dirty.value) return Promise.resolve(true)
  leaveConfirmation ??= confirmDevtoolsAction(
    t('core.devtools.unsavedTitle'),
    t('core.devtools.unsavedHint')
  ).finally(() => {
    leaveConfirmation = null
  })
  return leaveConfirmation
}
defineExpose({ canLeave })

const showEntry = (entry: StorageEntry) => {
  creating.value = false
  selectedKey.value = entry.key
  editorKey.value = entry.key
  editorValue.value = entry.value
  originalValue.value = entry.value
}

const loadEntries = () => {
  try {
    entries.value = readStorageEntries(currentStorage())
    error.value = ''
    if (!dirty.value && !creating.value) {
      const selected = entries.value.find(entry => entry.key === selectedKey.value)
      if (selected) showEntry(selected)
      else selectedKey.value = null
    }
  } catch {
    error.value = t('core.devtools.storageUnavailable')
    entries.value = []
  }
}
onMounted(loadEntries)

const selectEntry = async (entry: StorageEntry) => {
  if (!creating.value && selectedKey.value === entry.key) return
  if (await canLeave()) showEntry(entry)
}

const refresh = async () => {
  if (!(await canLeave())) return
  selectedKey.value = null
  creating.value = false
  loadEntries()
}

const changeScope = async (value: string | number) => {
  if (String(value) === scope.value || !(await canLeave())) return
  scope.value = String(value)
  search.value = ''
  selectedKey.value = null
  creating.value = false
  loadEntries()
}

const createEntry = async () => {
  if (!(await canLeave())) return
  selectedKey.value = null
  creating.value = true
  editorKey.value = ''
  editorValue.value = ''
  originalValue.value = ''
}

const saveEntry = async () => {
  if (saving.value || (creating.value && !editorKey.value.trim())) return
  saving.value = true
  try {
    const storage = currentStorage()
    const current = storage.getItem(editorKey.value)
    if (
      (creating.value && current !== null) ||
      (!creating.value && current !== originalValue.value)
    ) {
      if (
        !(await confirmDevtoolsAction(
          t('core.devtools.overwriteTitle'),
          t('core.devtools.overwriteHint')
        ))
      )
        return
    }
    storage.setItem(editorKey.value, editorValue.value)
    showEntry({ key: editorKey.value, value: editorValue.value, type: 'text', bytes: 0 })
    loadEntries()
    message.success(t('core.devtools.saved'))
  } catch {
    message.error(t('core.devtools.storageWriteFailed'))
  } finally {
    saving.value = false
  }
}

const removeEntry = async () => {
  const key = selectedKey.value
  if (key === null || saving.value) return
  try {
    const storage = currentStorage()
    if (
      !(await confirmDevtoolsAction(
        t('core.devtools.deleteTitle'),
        t(dirty.value ? 'core.devtools.deleteUnsavedHint' : 'core.devtools.deleteHint', { key })
      ))
    )
      return
    storage.removeItem(key)
    selectedKey.value = null
    editorValue.value = ''
    originalValue.value = ''
    loadEntries()
  } catch {
    message.error(t('core.devtools.storageWriteFailed'))
  }
}

const clearStorage = async () => {
  if (!(await canLeave())) return
  try {
    const storage = currentStorage()
    if (
      !(await confirmDevtoolsAction(
        t('core.devtools.clearTitle'),
        t('core.devtools.clearHint', {
          scope: scope.value === 'local' ? 'localStorage' : 'sessionStorage',
          count: entries.value.length,
        })
      ))
    )
      return
    storage.clear()
    selectedKey.value = null
    creating.value = false
    loadEntries()
  } catch {
    message.error(t('core.devtools.storageWriteFailed'))
  }
}

const formatJson = () => {
  try {
    editorValue.value = JSON.stringify(JSON.parse(editorValue.value), null, 2)
  } catch {
    message.error(t('core.devtools.invalidJson'))
  }
}

useEventListener(window, 'storage', event => {
  if (event.storageArea === currentStorage()) loadEntries()
})
useEventListener(window, 'beforeunload', event => {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
})
</script>

<template>
  <div class="devtools-toolbar">
    <a-segmented :value="scope" :options="scopeOptions" @change="changeScope" />
    <a-space>
      <a-button :aria-label="t('core.devtools.refresh')" @click="refresh"
        ><ReloadOutlined
      /></a-button>
      <a-button type="primary" @click="createEntry"
        ><PlusOutlined />{{ t('core.devtools.newEntry') }}</a-button
      >
    </a-space>
  </div>
  <a-alert v-if="error" type="error" :message="error" show-icon />
  <a-input
    v-model:value="search"
    :placeholder="t('core.devtools.searchStorage')"
    :aria-label="t('core.devtools.searchStorage')"
    allow-clear
  />
  <div class="devtools-toolbar">
    <span class="devtools-muted">{{
      t('core.devtools.storageCount', { count: entries.length, size: totalSize })
    }}</span>
    <a-button
      type="text"
      danger
      size="small"
      :disabled="entries.length === 0 || !!error"
      @click="clearStorage"
      >{{ t('core.devtools.clearScope') }}</a-button
    >
  </div>
  <div class="storage-layout">
    <div class="storage-list">
      <a-table
        :columns="columns"
        :data-source="filteredEntries"
        row-key="key"
        size="small"
        table-layout="fixed"
        :pagination="{ pageSize: 6, showSizeChanger: false, hideOnSinglePage: true }"
        :row-selection="{ type: 'radio', selectedRowKeys, onSelect: selectEntry, columnWidth: 32 }"
        :custom-row="(record: StorageEntry) => ({ onClick: () => selectEntry(record) })"
      >
        <template #emptyText>
          <NoData
            :description="t(search ? 'core.devtools.noMatches' : 'core.devtools.emptyStorage')"
          />
        </template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'key'">
            <button class="devtools-route-button" @click.stop="selectEntry(record)">
              {{ record.key || '""' }}
            </button>
            <div class="storage-preview">{{ record.value.slice(0, 90) }}</div>
          </template>
          <div v-else-if="column.key === 'type'" class="storage-type">
            <a-tag>{{ record.type === 'json' ? 'JSON' : t('core.devtools.text') }}</a-tag>
            <span class="devtools-muted">{{ formatBytes(record.bytes) }}</span>
          </div>
        </template>
      </a-table>
    </div>
    <section v-if="hasEditor" class="devtools-section storage-editor">
      <div class="devtools-toolbar">
        <h3>{{ t(creating ? 'core.devtools.newEntry' : 'core.devtools.editValue') }}</h3>
        <a-tag v-if="dirty" color="warning">{{ t('core.devtools.unsaved') }}</a-tag>
      </div>
      <a-form :model="{ key: editorKey, value: editorValue }" layout="vertical" @finish="saveEntry">
        <a-form-item
          name="key"
          :label="t('core.devtools.storageKey')"
          :rules="
            creating
              ? [
                  {
                    required: true,
                    whitespace: true,
                    message: t('core.devtools.storageKeyRequired'),
                  },
                ]
              : []
          "
        >
          <a-input
            v-if="creating"
            v-model:value="editorKey"
            :disabled="saving"
            :aria-label="t('core.devtools.storageKey')"
          />
          <code v-else class="devtools-code">{{ editorKey || '""' }}</code>
        </a-form-item>
        <a-form-item name="value" :label="t('core.devtools.storageValue')">
          <a-textarea
            v-model:value="editorValue"
            :disabled="saving"
            :auto-size="{ minRows: 6, maxRows: 18 }"
            :aria-label="t('core.devtools.storageValue')"
            class="value-input"
            spellcheck="false"
          />
        </a-form-item>
        <div class="devtools-toolbar">
          <a-space wrap>
            <a-button :disabled="saving" @click="formatJson">{{
              t('core.devtools.formatJson')
            }}</a-button>
            <a-button @click="copyDevtoolsText(editorValue)"
              ><CopyOutlined />{{ t('core.devtools.copyValue') }}</a-button
            >
          </a-space>
          <a-space>
            <a-button v-if="!creating" danger :disabled="saving" @click="removeEntry"
              ><DeleteOutlined />{{ t('core.devtools.delete') }}</a-button
            >
            <a-button
              type="primary"
              html-type="submit"
              :loading="saving"
              :disabled="creating ? !editorKey.trim() : !dirty"
              >{{ t('core.devtools.save') }}</a-button
            >
          </a-space>
        </div>
      </a-form>
    </section>
    <NoData v-else class="storage-empty" :description="t('core.devtools.selectStorage')" />
  </div>
  <p class="devtools-muted">{{ t('core.devtools.storageHint') }}</p>
</template>

<style scoped>
.storage-layout {
  display: grid;
  grid-template-columns: minmax(0, 0.85fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.storage-list {
  min-width: 0;
}
.storage-type {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}
.storage-empty {
  align-self: center;
  margin: 48px 16px;
}
.storage-preview {
  margin-top: 4px;
  max-width: 380px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.storage-editor {
  min-width: 0;
}
.value-input {
  font-family: var(--font-monospace);
  font-size: 12px;
}
@media (max-width: 850px) {
  .storage-layout {
    grid-template-columns: 1fr;
  }
}
</style>
