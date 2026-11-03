<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { getConfig, saveConfig } from '@/utils/config'
import { useSettingsSectionLayout, type SettingsLayoutMode } from './useSettingsSectionLayout'
import SettingsPageToolbar from './SettingsPageToolbar.vue'

defineProps<{ loading: boolean }>()
const activeKey = defineModel<string>('activeKey', { required: true })
const { t } = useI18n()
const layoutMode = ref<SettingsLayoutMode>('single')
const layoutReady = ref(false)
const savingLayout = ref(false)
const {
  layout,
  shell,
  sections,
  activeSection,
  navigationTop,
  effectiveDual,
  hasNavigation,
  scrollToSection,
} = useSettingsSectionLayout(activeKey, layoutMode)
const tabs = computed(() => [
  { key: 'basic', title: t('core.setting.tab.basic') },
  { key: 'function', title: t('core.setting.tab.function') },
  { key: 'notify', title: t('core.setting.tab.notify') },
  { key: 'advanced', title: t('core.setting.tab.advanced') },
  { key: 'others', title: t('core.setting.tab.others') },
])
let disposed = false

onMounted(async () => {
  try {
    const config = await getConfig()
    if (!disposed) layoutMode.value = config.settingsLayoutMode === 'dual' ? 'dual' : 'single'
  } catch {
    if (!disposed) message.error(t('core.setting.layout.loadFailed'))
  } finally {
    if (!disposed) layoutReady.value = true
  }
})

onBeforeUnmount(() => {
  disposed = true
})

async function changeLayout(value: unknown) {
  if ((value !== 'single' && value !== 'dual') || value === layoutMode.value || savingLayout.value)
    return
  const previous = layoutMode.value
  const operation = beginAnalyticsOperation('settings_change_finished')
  const fields = {
    setting_kind: 'other',
    setting_key: 'settings_layout',
    value_kind: value === 'single' ? 'default' : 'custom',
  } as const
  savingLayout.value = true
  layoutMode.value = value
  try {
    await saveConfig({ settingsLayoutMode: value })
    operation.finish({ ...fields, outcome: 'success' })
  } catch {
    operation.finish({ ...fields, outcome: 'failure' })
    if (!disposed) {
      layoutMode.value = previous
      message.error(t('core.setting.layout.saveFailed'))
    }
  } finally {
    if (!disposed) savingLayout.value = false
  }
}
</script>

<template>
  <div
    ref="layout"
    class="settings-content settings-section-layout"
    :data-layout-mode="layoutMode"
    :data-effective-layout="effectiveDual ? 'dual' : 'single'"
    :aria-busy="loading"
  >
    <div
      ref="shell"
      class="settings-shell"
      :class="{
        'settings-shell--with-nav': hasNavigation,
        'settings-shell--dual': effectiveDual,
        'settings-shell--about': activeKey === 'others',
      }"
    >
      <div class="settings-shell-main">
        <!-- 页面标题跟卡片列同一个容器，居中后标题、页签、卡片三者左边缘始终对齐 -->
        <div class="settings-shell-header">
          <div class="settings-title"><slot name="header" /></div>
          <SettingsPageToolbar
            :mode="layoutMode"
            :show-layout="activeKey !== 'others'"
            :disabled="!layoutReady"
            :saving-layout="savingLayout"
            @layout-change="changeLayout"
          />
        </div>
        <a-tabs v-model:active-key="activeKey" :animated="false" class="settings-tabs">
          <a-tab-pane v-for="tab in tabs" :key="tab.key" :tab="tab.title">
            <div class="settings-pane">
              <slot :name="tab.key" />
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>

      <nav
        v-if="hasNavigation"
        class="settings-section-navigation"
        :aria-label="t('core.setting.navigation.ariaLabel')"
        :style="{ top: `${navigationTop}px` }"
      >
        <div class="navigation-title">
          {{ t('core.setting.navigation.title') }}
        </div>
        <ul class="navigation-list">
          <li v-for="section in sections" :key="section.id">
            <button
              type="button"
              class="navigation-link"
              :class="{
                'navigation-link--active': activeSection === section.id,
              }"
              :aria-current="activeSection === section.id ? 'location' : undefined"
              :aria-controls="section.id"
              @click="scrollToSection(section)"
            >
              {{ section.title }}
            </button>
          </li>
        </ul>
        <div class="navigation-save-note">
          <InfoCircleOutlined aria-hidden="true" />
          <span>{{ t('core.setting.toolbar.autoSave') }}</span>
        </div>
      </nav>
    </div>
  </div>
</template>

<style scoped>
/* 卡片与目录共用限宽容器，标题和页签保持同一条左边缘。 */
.settings-section-layout {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}

.settings-shell {
  position: relative;
  display: flex;
  flex: 1;
  justify-content: center;
  width: 100%;
  max-width: 1040px;
  min-height: 0;
  margin: 0 auto;
}

.settings-shell--with-nav {
  max-width: 1240px;
}

.settings-shell--dual {
  max-width: 1440px;
}

.settings-shell--about {
  max-width: 1240px;
}

.settings-shell-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.settings-shell-header {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 24px;
  margin-bottom: 16px;
}

.settings-title {
  min-width: 0;
}

.settings-tabs {
  flex: 1;
  min-height: 0;
}

.settings-tabs :deep(.ant-tabs-nav) {
  flex: 0 0 auto;
  margin: 0;
}

.settings-tabs :deep(.ant-tabs-nav::before) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.settings-tabs :deep(.ant-tabs-content-holder) {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  scrollbar-gutter: stable;
  overflow-anchor: none;
}

/* 标题和页签占满整体限宽，只有滚动卡片列为右侧目录留位。 */
.settings-shell--with-nav .settings-tabs :deep(.ant-tabs-content-holder) {
  margin-right: 184px;
}

/* 页签：无边框、无填充，只用字重与下划线指示当前项 */
.settings-tabs :deep(.ant-tabs-tab) {
  padding: 10px 0 14px;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  transition: color 0.16s ease;
}

.settings-tabs :deep(.ant-tabs-tab + .ant-tabs-tab) {
  margin-left: 28px;
}

.settings-tabs :deep(.ant-tabs-tab:hover),
.settings-tabs :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: var(--ant-color-primary);
}

.settings-tabs :deep(.ant-tabs-ink-bar) {
  height: 2px;
  border-radius: 1px;
  background: var(--ant-color-primary);
}

.settings-tabs :deep(.tab-content) {
  width: 100%;
  padding: 22px 2px 24px 0;
}

.settings-tabs :deep(.settings-card-grid) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1px;
  column-gap: 16px;
  align-items: start;
}

.settings-tabs :deep(.settings-card-grid > *) {
  min-width: 0;
}

.settings-tabs :deep(.section-header > h3:focus-visible) {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 4px;
}

.settings-section-navigation {
  position: absolute;
  right: 0;
  display: block;
  width: 160px;
  max-height: calc(100% - 160px);
  padding: 12px 0;
  overflow-y: auto;
}

.navigation-title {
  margin-bottom: 12px;
  padding-left: 12px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.navigation-list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.navigation-link {
  position: relative;
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: 0;
  border-radius: 0 5px 5px 0;
  background: transparent;
  color: var(--ant-color-text-secondary);
  font: inherit;
  font-size: 12px;
  line-height: 20px;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
  transition:
    color 0.16s ease,
    background 0.16s ease;
}

.navigation-link:hover {
  color: var(--ant-color-text);
  background: var(--ant-color-fill-quaternary);
}

.navigation-link--active {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.navigation-link--active::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -1px;
  width: 2px;
  background: var(--ant-color-primary);
  content: '';
}

.navigation-link:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.navigation-save-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 24px 0 0 12px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
</style>
