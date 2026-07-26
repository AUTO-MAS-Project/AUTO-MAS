<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons-vue'
import { useTheme } from '@/composables/useTheme.ts'
import type { PageDeclaration } from '@/router/pageDeclarations.ts'
import AppSiderMenu from './AppSiderMenu.vue'
import GlobalSearch from './GlobalSearch.vue'

const props = defineProps<{
  mainItems: PageDeclaration[]
  bottomItems: PageDeclaration[]
  devItems: PageDeclaration[]
  selectedKeys: string[]
  collapsed: boolean
  isDevelopment: boolean
}>()

const emit = defineEmits<{
  (e: 'menu-click', path: string): void
  (e: 'search', keyword: string): void
  (e: 'toggle-collapse'): void
}>()

const { isDark, setThemeMode } = useTheme()
const theme = computed(() => (isDark.value ? 'dark' : 'light'))

const siderWidth = computed(() =>
  props.collapsed ? 'var(--v6-sidebar-width-collapsed)' : 'var(--v6-sidebar-width)'
)

// 全局搜索数据源之一：导航页面声明（含开发页，仅开发环境）
const searchPages = computed(() =>
  props.isDevelopment
    ? [...props.mainItems, ...props.devItems, ...props.bottomItems]
    : [...props.mainItems, ...props.bottomItems]
)

const handleMenuClick = (path: string) => emit('menu-click', path)
const handleToggle = () => {
  emit('toggle-collapse')
}
const toggleTheme = () => setThemeMode(isDark.value ? 'light' : 'dark')
const handleGlobalSearch = (keyword: string) => emit('search', keyword)

const handleKeydown = (event: KeyboardEvent) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'b') {
    event.preventDefault()
    emit('toggle-collapse')
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <a-layout-sider
    id="app-sider"
    :width="siderWidth"
    :theme="theme"
    class="app-sider"
    :class="{ 'app-sider--collapsed': collapsed }"
    :collapsed="collapsed"
    :collapsed-width="56"
    :style="{
      background: 'var(--app-layout-sider-bg, var(--v6-vibrancy-sidebar))',
      borderRight: '0.5px solid var(--v6-color-border)',
    }"
    role="navigation"
    aria-label="应用侧边导航"
  >
    <div class="sider-content">
      <div class="sider-top">
        <button
          type="button"
          class="collapse-toggle"
          :aria-label="collapsed ? '展开侧边栏' : '折叠侧边栏'"
          :aria-expanded="!collapsed"
          aria-controls="app-sider"
          :title="collapsed ? '展开侧边栏 (Ctrl+B)' : '折叠侧边栏 (Ctrl+B)'"
          @click="handleToggle"
        >
          <MenuUnfoldOutlined v-if="collapsed" aria-hidden="true" />
          <MenuFoldOutlined v-else aria-hidden="true" />
          <span class="toggle-text" :aria-hidden="collapsed">收起</span>
        </button>

        <div class="sider-search" :class="{ 'sider-search--collapsed': collapsed }">
          <GlobalSearch :pages="searchPages" :collapsed="collapsed" @search="handleGlobalSearch" />
        </div>

        <AppSiderMenu
          :items="mainItems"
          :selected-keys="selectedKeys"
          :theme="theme"
          :collapsed="collapsed"
          @click="handleMenuClick"
        />

        <AppSiderMenu
          v-if="isDevelopment"
          :items="devItems"
          :selected-keys="selectedKeys"
          :theme="theme"
          section-label="开发"
          class="dev-menu"
          :collapsed="collapsed"
          @click="handleMenuClick"
        />
      </div>

      <div class="sider-bottom">
        <button
          type="button"
          class="sider-theme-toggle"
          :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
          :title="isDark ? '浅色模式' : '深色模式'"
          @click="toggleTheme"
        >
          <!-- @ant-design/icons-vue 无 Sun/Moon 图标，此处内联等效 SVG：
               深色模式下显示太阳（点击回浅色），浅色模式下显示月亮（点击入深色） -->
          <svg
            v-if="isDark"
            class="sider-theme-icon sider-theme-icon--sun"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            aria-hidden="true"
            focusable="false"
          >
            <circle cx="12" cy="12" r="4.2" />
            <path
              d="M12 2.6v2.6M12 18.8v2.6M2.6 12h2.6M18.8 12h2.6M5.35 5.35l1.84 1.84M16.81 16.81l1.84 1.84M18.65 5.35l-1.84 1.84M7.19 16.81l-1.84 1.84"
            />
          </svg>
          <svg
            v-else
            class="sider-theme-icon sider-theme-icon--moon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <path d="M20.6 14.2A8.6 8.6 0 1 1 9.8 3.4a6.8 6.8 0 0 0 10.8 10.8Z" />
          </svg>
          <span class="sider-tool-text" :aria-hidden="collapsed">
            {{ isDark ? '浅色模式' : '深色模式' }}
          </span>
        </button>
        <AppSiderMenu
          :items="bottomItems"
          :selected-keys="selectedKeys"
          :theme="theme"
          :collapsed="collapsed"
          @click="handleMenuClick"
        />
      </div>
    </div>
  </a-layout-sider>
</template>

<style scoped>
/*
 * 折叠动画布局稳定性契约（与 AppSiderMenu / GlobalSearch 同构）：
 * 1. 每一行（收起钮 / 搜索钮 / 菜单项 / 主题切换）两态行高固定 40px；
 * 2. 图标固定 20px 列居中（18px 字形），两态 padding 均为 0 10px、
 *    外框均为 calc(100% - 8px) 水平居中 → 图标 x 位置全程不漂移；
 * 3. 文字标签 nowrap + overflow 裁剪，以 max-width/opacity/transform 隐藏，
 *    不用 v-if 移除；
 * 4. transition 只含 width/opacity/transform/颜色类属性，
 *    height/padding/margin 等纵向布局属性一律不做动画。
 */
.app-sider {
  position: relative;
  z-index: var(--v6-z-sidebar);
  backdrop-filter: var(--v6-backdrop-sidebar);
  -webkit-backdrop-filter: var(--v6-backdrop-sidebar);
  user-select: none;
  -webkit-user-select: none;
  overflow: hidden;
  transition:
    width var(--v6-motion-base) var(--v6-ease-out),
    min-width var(--v6-motion-base) var(--v6-ease-out),
    max-width var(--v6-motion-base) var(--v6-ease-out),
    flex-basis var(--v6-motion-base) var(--v6-ease-out);
}

.app-sider :deep(.ant-layout-sider-children) {
  width: 100%;
  overflow: hidden;
}

.sider-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 10px 4px;
  min-width: 0;
}

.sider-top {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
  overflow: hidden;
}

.sider-bottom {
  margin-top: auto;
}

.sider-search {
  width: calc(100% - 8px);
  height: 40px;
  margin: 0 auto;
  display: flex;
  align-items: center;
}

/* 与下方菜单项(AppSiderMenu)完全同构：40px 行高、0 10px 内边距、
   20px 图标列（18px 字形）、6px 间距；静态观感同菜单项（字色/字号/悬停） */
.sider-theme-toggle {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  width: calc(100% - 8px);
  height: 40px;
  margin: 0 auto var(--v6-space-1);
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text);
  font: inherit;
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-normal);
  cursor: pointer;
  -webkit-app-region: no-drag;
  overflow: hidden;
  white-space: nowrap;
  transition:
    background var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
}

/* 图标固定列宽：色值与菜单项图标一致（次级文字色，悬停回主文字色） */
.sider-theme-icon {
  flex: 0 0 20px;
  width: 20px;
  height: 18px;
  color: var(--ant-color-text-secondary);
  transition: color var(--v6-motion-fast) var(--v6-ease-out);
}

.sider-theme-toggle:hover {
  color: var(--ant-color-text);
  background: var(--v6-vibrancy-hover);
}

.sider-theme-toggle:hover .sider-theme-icon {
  color: var(--ant-color-text);
}

.sider-theme-toggle:focus-visible {
  outline: none;
  box-shadow: var(--v6-focus-ring-inset);
}

.sider-tool-text {
  max-width: 96px;
  overflow: hidden;
  opacity: 1;
  white-space: nowrap;
  transform: translateX(0);
  transition:
    max-width var(--v6-motion-base) var(--v6-ease-out),
    opacity var(--v6-motion-fast) var(--v6-ease-out),
    transform var(--v6-motion-base) var(--v6-ease-out);
}

.collapse-toggle {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  width: calc(100% - 8px);
  height: 40px;
  margin: 0 auto;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: var(--v6-radius-control);
  background: transparent;
  color: var(--ant-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  transition:
    background var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out),
    border-color var(--v6-motion-fast) var(--v6-ease-out);
  -webkit-app-region: no-drag;
}

.collapse-toggle :deep(.anticon) {
  flex: 0 0 20px;
  width: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
}

.collapse-toggle:hover {
  background: var(--v6-vibrancy-hover);
  color: var(--ant-color-text);
}

.collapse-toggle:focus-visible {
  outline: none;
  box-shadow: var(--v6-focus-ring-inset);
}

.toggle-text {
  display: inline-block;
  max-width: 48px;
  overflow: hidden;
  opacity: 1;
  line-height: 1;
  white-space: nowrap;
  transform: translateX(0);
  transition:
    max-width var(--v6-motion-base) var(--v6-ease-out),
    opacity var(--v6-motion-fast) var(--v6-ease-out),
    transform var(--v6-motion-base) var(--v6-ease-out);
}

/* 折叠态只隐藏文字：行几何（高/宽公式/内边距/图标列）与展开态完全一致 */
.app-sider--collapsed .toggle-text {
  max-width: 0;
  opacity: 0;
  pointer-events: none;
  transform: translateX(-6px);
}

.app-sider--collapsed .sider-tool-text {
  max-width: 0;
  opacity: 0;
  transform: translateX(-8px);
}

.dev-menu {
  margin-top: var(--v6-space-4);
  padding-top: var(--v6-space-4);
  border-top: 1px solid var(--ant-color-border);
}

@media (prefers-reduced-motion: reduce) {
  .app-sider {
    transition: none;
  }

  .collapse-toggle {
    transition: none;
  }

  .toggle-text {
    transition: none;
  }

  .sider-theme-toggle,
  .sider-theme-icon,
  .sider-tool-text {
    transition: none;
  }
}

:global(:root[data-perf-mode='low']) .app-sider,
:global(:root[data-perf-mode='low']) .collapse-toggle,
:global(:root[data-perf-mode='low']) .toggle-text {
  transition: none;
}

:global(:root[data-perf-mode='low']) .sider-theme-toggle,
:global(:root[data-perf-mode='low']) .sider-theme-icon,
:global(:root[data-perf-mode='low']) .sider-tool-text {
  transition: none;
}
</style>
