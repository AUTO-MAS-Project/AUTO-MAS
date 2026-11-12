<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { EditOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { DEFAULT_TRAY_ITEMS, TRAY_ACTION_OPTIONS, type TrayMenuItem } from '@/types/tray'
import TrayMenuDialog from './TrayMenuDialog.vue'

const { t } = useI18n()
const logger = window.electronAPI?.getLogger?.('托盘菜单')
const items = ref<TrayMenuItem[]>([])
const loading = ref(true)
const loadFailed = ref(false)
const editorOpen = ref(false)
let disposed = false

const preview = computed(() =>
  items.value
    .slice(0, 3)
    .map(item => item.label)
    .join(' · ')
)

const load = async () => {
  loading.value = true
  loadFailed.value = false
  try {
    const config = await window.electronAPI?.loadConfig()
    if (!config) throw new Error('未读取到托盘配置')
    const saved = config.UI?.TrayItems
    const savedItems = Array.isArray(saved)
      ? saved.flatMap((item: unknown) => {
          if (!item || typeof item !== 'object') return []
          const value = item as Record<string, unknown>
          const option = TRAY_ACTION_OPTIONS.find(option => option.value === value.action)
          if (!option) return []
          return [
            {
              id: typeof value.id === 'string' && value.id ? value.id : crypto.randomUUID(),
              label: typeof value.label === 'string' ? value.label : option.label,
              action: option.value,
              taskId: typeof value.taskId === 'string' ? value.taskId.trim() : undefined,
            },
          ]
        })
      : []
    if (!disposed) {
      items.value = (savedItems.length ? savedItems : DEFAULT_TRAY_ITEMS).map(item => ({ ...item }))
    }
  } catch (error) {
    logger?.warn(`读取托盘菜单配置失败: ${error instanceof Error ? error.message : String(error)}`)
    if (!disposed) loadFailed.value = true
  } finally {
    if (!disposed) loading.value = false
  }
}

const handleSaved = (savedItems: TrayMenuItem[]) => {
  items.value = savedItems.map(item => ({ ...item }))
  editorOpen.value = false
}

onMounted(() => void load())
onBeforeUnmount(() => {
  disposed = true
})
</script>

<template>
  <div class="tray-menu-summary" :aria-busy="loading">
    <span v-if="loadFailed" class="tray-menu-preview tray-menu-preview--error" role="alert">
      {{ t('core.setting.tray.loadFailed') }}
    </span>
    <span v-else-if="!loading" class="tray-menu-preview">{{ preview }}</span>
    <a-button v-if="loadFailed" size="small" @click="load">
      {{ t('core.setting.tray.retry') }}
    </a-button>
    <a-button v-else size="small" :loading="loading" :disabled="loading" @click="editorOpen = true">
      <template #icon><EditOutlined /></template>
      {{ t('core.setting.tray.edit') }}
    </a-button>
    <TrayMenuDialog
      v-if="editorOpen"
      :saved-items="items"
      @saved="handleSaved"
      @close="editorOpen = false"
    />
  </div>
</template>

<style scoped>
.tray-menu-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  min-width: 0;
}

.tray-menu-preview {
  min-width: 0;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tray-menu-preview--error {
  color: var(--ant-color-error);
}
</style>
