<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BulbOutlined, ProfileOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useTheme } from '@/composables/useTheme'

const props = defineProps<{
  disabled: boolean
  navigationVisible: boolean
  navigationAvailable: boolean
  savingNavigation: boolean
}>()
const emit = defineEmits<{ 'toggle-navigation': [] }>()
const { t } = useI18n()
const { isDark, activeAppearance, setThemeMode } = useTheme()
const changingTheme = ref(false)
const themeToggleLabel = computed(() =>
  t(isDark.value ? 'core.setting.toolbar.switchToLight' : 'core.setting.toolbar.switchToDark')
)
const themeTooltip = computed(() =>
  activeAppearance.value ? t('core.setting.toolbar.appearanceThemeLocked') : themeToggleLabel.value
)
const navigationLabel = computed(() =>
  t(props.navigationVisible ? 'core.setting.navigation.hide' : 'core.setting.navigation.show')
)
let disposed = false

onBeforeUnmount(() => {
  disposed = true
})

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
    <a-tooltip
      v-if="navigationAvailable"
      :title="navigationLabel"
      :trigger="['hover', 'focus']"
      placement="bottomRight"
    >
      <a-button
        class="settings-navigation-toggle"
        :aria-label="navigationLabel"
        :aria-pressed="navigationVisible"
        :aria-controls="navigationVisible ? 'settings-section-navigation' : undefined"
        :aria-busy="savingNavigation"
        :loading="savingNavigation"
        :disabled="disabled || savingNavigation"
        @click="emit('toggle-navigation')"
      >
        <template #icon><ProfileOutlined aria-hidden="true" /></template>
      </a-button>
    </a-tooltip>
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

.settings-navigation-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border-color: var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text-secondary);
}

.settings-navigation-toggle[aria-pressed='true'] {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.settings-navigation-toggle:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.settings-navigation-toggle:hover:not(:disabled) {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.settings-navigation-toggle:disabled {
  color: var(--ant-color-text-disabled);
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

html:not(.dark) .settings-theme-toggle {
  border-color: color-mix(in srgb, var(--ant-color-border) 55%, var(--ant-color-text) 45%);
}

@media (max-width: 690px) {
  .settings-page-toolbar {
    justify-content: flex-start;
    gap: 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .settings-theme-toggle {
    animation: none;
    transition: none;
  }
}
</style>
