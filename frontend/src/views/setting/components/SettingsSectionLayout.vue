<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ProfileOutlined, RightOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useSettingsSectionLayout } from './useSettingsSectionLayout'
import { getConfig, saveConfig } from '@/utils/config'
import { beginAnalyticsOperation } from '@/utils/analytics'

defineProps<{ loading: boolean }>()
const activeKey = defineModel<string>('activeKey', { required: true })
const { t } = useI18n()
const layoutReady = ref(false)
// 目录显隐是持久化偏好，窗口宽度只决定列数，不决定目录。
const navigationVisible = ref(true)
const savingNavigation = ref(false)
const {
  layout,
  shell,
  sections,
  activeSection,
  navigationTop,
  effectiveDual,
  navigationAvailable,
  hasNavigation,
  scrollToSection,
} = useSettingsSectionLayout(activeKey, navigationVisible)
const navigationLabel = computed(() =>
  t(hasNavigation.value ? 'core.setting.navigation.hide' : 'core.setting.navigation.show')
)
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
    if (!disposed) navigationVisible.value = config.settingsShowNavigation !== false
  } catch {
    if (!disposed) message.error(t('core.setting.navigation.loadFailed'))
  } finally {
    if (!disposed) layoutReady.value = true
  }
})

onBeforeUnmount(() => {
  disposed = true
})

async function toggleNavigation() {
  if (savingNavigation.value) return
  const previous = navigationVisible.value
  const next = !previous
  const operation = beginAnalyticsOperation('settings_change_finished')
  const fields = {
    setting_kind: 'other',
    setting_key: 'settings_navigation',
    value_kind: next ? 'enabled' : 'disabled',
  } as const
  savingNavigation.value = true
  navigationVisible.value = next
  try {
    await saveConfig({ settingsShowNavigation: next })
    operation.finish({ ...fields, outcome: 'success' })
  } catch {
    operation.finish({ ...fields, outcome: 'failure' })
    if (!disposed) {
      navigationVisible.value = previous
      message.error(t('core.setting.navigation.saveFailed'))
    }
  } finally {
    if (!disposed) savingNavigation.value = false
  }
}
</script>

<template>
  <div
    ref="layout"
    class="settings-content settings-section-layout"
    :data-effective-layout="effectiveDual ? 'dual' : 'single'"
    :aria-busy="loading"
  >
    <div
      ref="shell"
      class="settings-shell"
      :class="{
        'settings-shell--navigation-available': navigationAvailable,
        'settings-shell--with-nav': hasNavigation,
        'settings-shell--dual': effectiveDual,
        'settings-shell--about': activeKey === 'others',
      }"
    >
      <div class="settings-shell-main">
        <!-- 页面标题跟卡片列同一个容器，居中后标题、页签、卡片三者左边缘始终对齐 -->
        <div class="settings-shell-header">
          <div class="settings-title"><slot name="header" /></div>
        </div>
        <a-tabs v-model:active-key="activeKey" :animated="false" class="settings-tabs">
          <a-tab-pane v-for="tab in tabs" :key="tab.key" :tab="tab.title">
            <div class="settings-pane">
              <slot :name="tab.key" />
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>

      <aside
        v-if="navigationAvailable"
        class="settings-navigation-panel"
        :class="{ 'settings-navigation-panel--collapsed': !hasNavigation }"
        :style="{ top: `${navigationTop}px` }"
      >
        <div class="navigation-header">
          <span v-if="hasNavigation" class="navigation-title">
            {{ t('core.setting.navigation.title') }}
          </span>
          <a-tooltip :title="navigationLabel" :trigger="['hover', 'focus']" placement="left">
            <a-button
              type="text"
              class="settings-navigation-toggle"
              :aria-label="navigationLabel"
              :aria-expanded="hasNavigation"
              aria-controls="settings-section-navigation"
              :aria-busy="savingNavigation"
              :loading="savingNavigation"
              :disabled="!layoutReady"
              @click="toggleNavigation"
            >
              <template #icon>
                <RightOutlined v-if="hasNavigation" aria-hidden="true" />
                <ProfileOutlined v-else aria-hidden="true" />
              </template>
            </a-button>
          </a-tooltip>
        </div>
        <nav
          v-show="hasNavigation"
          id="settings-section-navigation"
          class="settings-section-navigation"
          :aria-label="t('core.setting.navigation.ariaLabel')"
        >
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
        </nav>
      </aside>
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

.settings-shell--navigation-available,
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
  flex: 0 0 auto;
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

/* 收起时仍为右侧入口留位，避免它覆盖设置控件。 */
.settings-shell--navigation-available .settings-tabs :deep(.ant-tabs-content-holder) {
  margin-right: 56px;
}

/* 标题和页签占满整体限宽，只有滚动卡片列为展开的目录留位。 */
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

.settings-navigation-panel {
  position: absolute;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  width: 160px;
  padding: 12px 0;
}

.settings-navigation-panel--collapsed {
  width: 32px;
}

.navigation-header {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-left: 12px;
}

.settings-navigation-panel--collapsed .navigation-header {
  padding-left: 0;
}

.navigation-title {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.settings-navigation-toggle {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--ant-color-text-secondary);
}

.settings-navigation-toggle:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.settings-section-navigation {
  min-height: 0;
  margin-top: 8px;
  overflow-y: auto;
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
  border-radius: 0 var(--ant-border-radius-sm) var(--ant-border-radius-sm) 0;
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
</style>
