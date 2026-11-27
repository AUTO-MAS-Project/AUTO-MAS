<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { CloudDownloadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import type { MascotSummary } from '@/types/mascotPack'
import { getConfig } from '@/utils/config'

defineProps<{
  outdatedCount: number
  updatingAll: boolean
}>()

defineEmits<{
  'update-all': []
}>()

const { t } = useI18n()
const { persistedAppearance, themeMode } = useTheme()
const mascots = ref<MascotSummary[]>([])
const mascotId = ref<string | null>(null)
const mascotEnabled = ref(true)
let unsubscribeMascot: (() => void) | undefined

const activeThemeLabel = computed(() => {
  if (persistedAppearance.value) return persistedAppearance.value.name
  if (themeMode.value === 'dark') return t('core.setting.themeMode.dark')
  if (themeMode.value === 'light') return t('core.setting.themeMode.light')
  return t('core.setting.themeMode.system')
})

const activeMascotLabel = computed(() => {
  if (!mascotEnabled.value) return t('core.themeStore.localStatus.mascotOff')
  if (mascotId.value) {
    return mascots.value.find(item => item.id === mascotId.value)?.name ?? mascotId.value
  }
  if (persistedAppearance.value?.mascotUrl) {
    return t('core.themeStore.localStatus.mascotFollowTheme')
  }
  return t('core.themeStore.localStatus.mascotNone')
})

const loadLocalMascot = async (): Promise<void> => {
  try {
    const [config, list] = await Promise.all([
      getConfig(),
      window.electronAPI.listMascots?.() ?? [],
    ])
    mascotId.value = config.desktopMascotId ?? null
    mascotEnabled.value = config.desktopMascotEnabled !== false
    mascots.value = list
  } catch {
    // 桌宠信息读取失败时保持回退文案，不影响商店主浏览。
  }
}

onMounted(() => {
  unsubscribeMascot = window.electronAPI.onMascotChanged?.(selection => {
    if (selection) {
      mascotId.value = selection.id
      mascotEnabled.value = selection.enabled
    } else {
      void loadLocalMascot()
    }
  })
  void loadLocalMascot()
})

onBeforeUnmount(() => {
  unsubscribeMascot?.()
})
</script>

<template>
  <div class="local-status-strip">
    <div class="local-status-pills">
      <span class="local-status-item">
        <span class="local-status-dot" aria-hidden="true" />
        <span class="local-status-label">{{ t('core.themeStore.localStatus.currentTheme') }}</span>
        <strong class="local-status-value">{{ activeThemeLabel }}</strong>
      </span>
      <span class="local-status-divider" aria-hidden="true" />
      <span class="local-status-item">
        <span class="local-status-label">{{ t('core.themeStore.localStatus.currentMascot') }}</span>
        <strong class="local-status-value">{{ activeMascotLabel }}</strong>
      </span>
    </div>

    <div v-if="outdatedCount > 0" class="local-status-updates">
      <a-tag color="warning" class="local-status-badge">
        {{ t('core.themeStore.localStatus.outdatedCount', { count: outdatedCount }) }}
      </a-tag>
      <a-button
        size="small"
        type="primary"
        ghost
        :loading="updatingAll"
        @click="$emit('update-all')"
      >
        <template #icon><CloudDownloadOutlined /></template>
        {{ t('core.themeStore.localStatus.updateAll') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.local-status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  margin-bottom: 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-fill-tertiary);
}

.local-status-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
  min-width: 0;
}

.local-status-item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.local-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ant-color-success);
}

.local-status-value {
  color: var(--ant-color-text);
  font-weight: 600;
}

.local-status-divider {
  width: 1px;
  height: 12px;
  background: var(--ant-color-border);
}

.local-status-updates {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.local-status-badge {
  margin-inline-end: 0;
}
</style>
