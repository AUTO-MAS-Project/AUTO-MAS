<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { EditOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { DEFAULT_TRAY_ITEMS, TRAY_ACTION_OPTIONS, type TrayMenuItem } from '@/types/tray'
import SettingRow from '@/components/ui/SettingRow.vue'
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
  <SettingRow :aria-busy="loading">
    <template #label>
      <span class="tray-menu-label">
        {{ t('core.setting.tray.section') }}
        <a-tooltip :title="t('core.setting.tray.sectionTip')" :trigger="['hover', 'focus']">
          <QuestionCircleOutlined class="tray-menu-hint" tabindex="0" />
        </a-tooltip>
      </span>
      <p
        class="tray-menu-description"
        :class="{ 'tray-menu-description--error': loadFailed }"
        :role="loadFailed ? 'alert' : undefined"
      >
        {{ loadFailed ? t('core.setting.tray.loadFailed') : loading ? '' : preview }}
      </p>
    </template>

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
  </SettingRow>
</template>

<style scoped>
.tray-menu-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.tray-menu-hint {
  color: var(--ant-color-text-quaternary);
  font-size: 14px;
  cursor: help;
}

.tray-menu-hint:hover,
.tray-menu-hint:focus-visible {
  color: var(--ant-color-primary);
}

.tray-menu-description {
  flex-basis: 100%;
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 400;
  line-height: 19px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tray-menu-description--error {
  color: var(--ant-color-error);
}
</style>
