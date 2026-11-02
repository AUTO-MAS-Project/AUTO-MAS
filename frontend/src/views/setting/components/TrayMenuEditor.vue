<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
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
    <div class="tray-menu-description">
      <div class="tray-menu-title">
        <span>{{ t('core.setting.tray.section') }}</span>
        <a-tooltip :title="t('core.setting.tray.sectionTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </div>
      <div v-if="!loading && !loadFailed" class="tray-menu-preview" :title="preview">
        {{ t('core.setting.tray.summary', { count: items.length }) }} · {{ preview }}
      </div>
      <div v-if="loadFailed" class="tray-menu-preview" role="alert">
        {{ t('core.setting.tray.loadFailed') }}
      </div>
    </div>
    <a-button v-if="loadFailed" size="small" @click="load">
      {{ t('core.setting.tray.retry') }}
    </a-button>
    <a-button v-else size="small" :loading="loading" :disabled="loading" @click="editorOpen = true">
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
  gap: 16px;
  padding-block: 8px;
}

.tray-menu-description {
  flex: 1;
  min-width: 0;
}

.tray-menu-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon,
.tray-menu-preview {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.tray-menu-preview {
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
