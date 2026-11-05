<script setup lang="ts">
import { computed, h, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BulbOutlined, CheckOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useTheme } from '@/composables/useTheme'
import type { SettingsLayoutMode } from './useSettingsSectionLayout'

const props = defineProps<{
  mode: SettingsLayoutMode
  showLayout: boolean
  disabled: boolean
  savingLayout: boolean
}>()
const emit = defineEmits<{ layoutChange: [value: SettingsLayoutMode] }>()
const { t } = useI18n()
const { isDark, activeAppearance, setThemeMode } = useTheme()
const changingTheme = ref(false)
const themeToggleLabel = computed(() =>
  t(isDark.value ? 'core.setting.toolbar.switchToLight' : 'core.setting.toolbar.switchToDark')
)
const themeTooltip = computed(() =>
  activeAppearance.value ? t('core.setting.toolbar.appearanceThemeLocked') : themeToggleLabel.value
)
const layoutOptions = computed(() => [
  {
    value: 'single',
    label: () => [layoutIcon('single'), t('core.setting.layout.single')],
  },
  {
    value: 'dual',
    label: () => [layoutIcon('dual'), t('core.setting.layout.dual')],
  },
])
let disposed = false

onBeforeUnmount(() => {
  disposed = true
})

function changeLayout(value: unknown) {
  if (props.disabled || props.savingLayout) return
  if (value === 'single' || value === 'dual') emit('layoutChange', value)
}

function layoutIcon(mode: SettingsLayoutMode) {
  const rectangles =
    mode === 'single'
      ? [
          { x: 2, y: 2, width: 12, height: 4 },
          { x: 2, y: 10, width: 12, height: 4 },
        ]
      : [
          { x: 2, y: 2, width: 4, height: 12 },
          { x: 10, y: 2, width: 4, height: 12 },
        ]
  return h(
    'svg',
    {
      class: 'settings-layout-icon',
      viewBox: '0 0 16 16',
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 1.2,
      'aria-hidden': true,
    },
    rectangles.map(rectangle => h('rect', { ...rectangle, rx: 1 }))
  )
}

async function toggleTheme() {
  if (props.disabled || changingTheme.value || activeAppearance.value) return
  changingTheme.value = true
  try {
    // 沿用主题保存、失败回退、过渡动画与唯一遥测入口。
    await setThemeMode(isDark.value ? 'light' : 'dark')
  } catch {
    if (!disposed) message.error(t('core.setting.basic.appearanceApplyFailed'))
  } finally {
    if (!disposed) changingTheme.value = false
  }
}
</script>

<template>
  <div class="settings-page-toolbar">
    <span class="settings-save-note">
      <CheckOutlined aria-hidden="true" />
      {{ t('core.setting.toolbar.autoSave') }}
    </span>
    <div v-if="showLayout" class="settings-layout-control">
      <span class="settings-layout-label" aria-hidden="true">
        {{ t('core.setting.layout.label') }}
      </span>
      <a-segmented
        class="settings-layout-selector"
        :value="mode"
        :options="layoutOptions"
        :aria-label="t('core.setting.layout.ariaLabel')"
        :aria-busy="savingLayout"
        :disabled="disabled || savingLayout"
        @change="changeLayout"
      />
    </div>
    <a-tooltip :title="themeTooltip" :trigger="['hover', 'focus']" placement="bottomRight">
      <span
        class="settings-theme-toggle-wrapper"
        :tabindex="activeAppearance ? 0 : undefined"
        :aria-label="activeAppearance ? themeTooltip : undefined"
      >
        <a-button
          class="settings-theme-toggle"
          :aria-label="themeToggleLabel"
          :aria-busy="changingTheme"
          :loading="changingTheme"
          :disabled="disabled || changingTheme || Boolean(activeAppearance)"
          @click="toggleTheme"
        >
          <template #icon><BulbOutlined aria-hidden="true" /></template>
        </a-button>
      </span>
    </a-tooltip>
  </div>
</template>

<style scoped>
.settings-page-toolbar {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 12px 16px;
  max-width: 100%;
}

.settings-save-note {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.settings-save-note :deep(.anticon) {
  font-size: 14px;
}

.settings-layout-control {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-right: 16px;
  border-right: 1px solid var(--ant-color-border);
}

.settings-layout-label {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.settings-layout-selector {
  flex-shrink: 0;
  padding: 3px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.settings-layout-selector :deep(.ant-segmented-item-label) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 27px;
  padding-inline: 10px;
  font-size: 12px;
  line-height: 27px;
}

.settings-layout-selector :deep(.ant-segmented-item:has(input:focus-visible)) {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.settings-layout-selector :deep(.settings-layout-icon) {
  flex-shrink: 0;
  width: 15px;
  height: 15px;
}

.settings-theme-toggle-wrapper {
  display: inline-flex;
  flex-shrink: 0;
}

.settings-theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border-color: var(--ant-color-border);
  border-radius: 7px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text-secondary);
}

.settings-theme-toggle:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.settings-theme-toggle:hover:not(:disabled) {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.settings-theme-toggle:disabled {
  color: var(--ant-color-text-disabled);
}

html:not(.dark) .settings-layout-selector {
  border-color: color-mix(in srgb, var(--ant-color-border) 92%, var(--ant-color-text) 8%);
}

html:not(.dark) .settings-layout-selector :deep(.ant-segmented-item-selected) {
  color: var(--ant-color-link);
  box-shadow: inset 0 0 0 1px var(--ant-color-text-tertiary);
}

html:not(.dark) .settings-theme-toggle {
  border-color: color-mix(in srgb, var(--ant-color-border) 55%, var(--ant-color-text) 45%);
}

@media (max-width: 690px) {
  .settings-page-toolbar {
    justify-content: flex-start;
    gap: 10px;
  }

  .settings-layout-label {
    display: none;
  }

  .settings-layout-control {
    gap: 0;
    padding-right: 10px;
  }

  .settings-layout-selector :deep(.ant-segmented-item-label) {
    padding-inline: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .settings-theme-toggle,
  .settings-layout-selector,
  .settings-layout-selector :deep(.ant-segmented-item),
  .settings-layout-selector :deep(.ant-segmented-thumb) {
    animation: none;
    transition: none;
  }
}
</style>
