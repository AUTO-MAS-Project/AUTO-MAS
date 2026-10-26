<template>
  <a-layout
    style="
      position: relative;
      z-index: 1;
      flex: 1;
      min-height: 0;
      overflow: hidden;
      background: transparent;
    "
  >
    <a-layout-sider
      :width="SIDER_WIDTH"
      :theme="isDark ? 'dark' : 'light'"
      :style="{
        background: 'var(--app-appearance-elevated-surface-bg, var(--ant-color-bg-elevated))',
        borderRight: '1px solid var(--ant-color-border)',
      }"
    >
      <div class="sider-content">
        <a-menu
          v-model:selected-keys="selectedKeys"
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          :items="mainMenuItems"
          @click="onMenuClick"
        />
        <!-- 测试路由分隔区域 -->
        <a-menu
          v-if="isDevelopment"
          v-model:selected-keys="selectedKeys"
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          class="dev-menu"
          :items="devMenuItems"
          @click="onMenuClick"
        />
        <a-menu
          v-model:selected-keys="selectedKeys"
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          class="bottom-menu"
          :items="bottomMenuItems"
          @click="onMenuClick"
        />
      </div>
    </a-layout-sider>

    <a-layout style="flex: 1; min-width: 0; background: transparent">
      <a-layout-content class="content-area">
        <router-view v-slot="{ Component, route: currentRoute }">
          <keep-alive :include="['SchedulerPage']">
            <component :is="Component" :key="currentRoute.path" />
          </keep-alive>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script lang="ts" setup>
import { isDevelopmentEnvironment as isDev } from '@/utils/environment'
import { useI18n } from 'vue-i18n'
import {
  BugOutlined,
  CalendarOutlined,
  CarryOutOutlined,
  ControlOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HistoryOutlined,
  HomeOutlined,
  SettingOutlined,
  SkinOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import { computed, nextTick, watch } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'
import { useRouteLock } from '../composables/useRouteLock.ts'
import type { MenuProps } from 'ant-design-vue'
import type { AppearanceMenuIconKey } from '@/types/appearance'
import { createAppearanceMenuIcon } from './appearanceMenuIcon'

const { t } = useI18n()

const SIDER_WIDTH = 160

const router = useRouter()
const route = useRoute()
const { isDark, activeAppearance } = useTheme()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()

// 内容区滚动复位：滚动容器是 .content-area（div），路由 scrollBehavior 管不到。
// 路径变化（页面切换）时回顶，避免旧页面的滚动位置被带到新页面；
// 仅查询参数变化（如页签切换）不重置。取容器沿用 .content-area 查询惯例。
watch(
  () => route.path,
  () =>
    void nextTick(() => {
      document.querySelector<HTMLElement>('.content-area')?.scrollTo({ top: 0 })
    })
)

// 菜单图标依次使用外观包的专属图标、默认图标和内置图标。
const icon =
  (key: AppearanceMenuIconKey, Comp: Component, menuIcons = activeAppearance.value?.menuIconUrls) =>
  () =>
    createAppearanceMenuIcon(key, Comp, menuIcons)

// 调试入口与路由同时要求开发构建和开发环境，避免指向已裁剪的页面。
const isDevelopment = import.meta.env.DEV && isDev

const mainMenuItems = computed(() => [
  { key: '/home', label: t('comp.home'), icon: icon('home', HomeOutlined) },
  { key: '/scripts', label: t('comp.scripts'), icon: icon('scripts', FileTextOutlined) },
  { key: '/plans', label: t('comp.plans'), icon: icon('plans', CalendarOutlined) },
  { key: '/emulators', label: t('comp.emulators'), icon: icon('emulators', DatabaseOutlined) },
  { key: '/queue', label: t('comp.queue'), icon: icon('queue', UnorderedListOutlined) },
  { key: '/scheduler', label: t('comp.scheduler'), icon: icon('scheduler', ControlOutlined) },
])

// 开发环境专用菜单项
const devMenuItems = computed(() => [
  { key: '/TestRouter', label: t('comp.testRoute'), icon: icon('testRouter', SettingOutlined) },
  { key: '/OCRdev', label: t('comp.ocrTest'), icon: icon('ocrDev', SettingOutlined) },
  {
    key: '/OverlayMaskDev',
    label: t('comp.overlayEasterEggTest'),
    icon: icon('overlayMaskDev', SettingOutlined),
  },
  ...(isDevelopment
    ? [
        {
          key: '/update-download-dev',
          label: t('comp.updateDownloadTest'),
          icon: icon('updateDownloadDev', BugOutlined),
        },
      ]
    : []),
])

const bottomMenuItems = computed(() => [
  { key: '/gamesign', label: t('comp.checkIns'), icon: icon('gameSign', CarryOutOutlined) },
  { key: '/history', label: t('comp.history'), icon: icon('history', HistoryOutlined) },
  { key: '/theme-store', label: t('comp.themeStore'), icon: icon('themeStore', SkinOutlined) },
  { key: '/settings', label: t('comp.settings'), icon: icon('settings', SettingOutlined) },
])

type MenuEntry = NonNullable<MenuProps['items']>[number]
type KeyedMenuEntry = Exclude<MenuEntry, null> & { key: string | number }

const hasMenuKey = (item: MenuEntry): item is KeyedMenuEntry =>
  item !== null && 'key' in item && item.key !== undefined

const flattenMenuItems = (items: readonly MenuEntry[]): MenuEntry[] => {
  const flattened: MenuEntry[] = []
  for (const item of items) {
    if (!item) continue
    flattened.push(item)
    if ('children' in item && item.children) {
      flattened.push(...flattenMenuItems(item.children))
    }
  }
  return flattened
}

const allItems = computed(() => [
  ...mainMenuItems.value,
  ...(isDevelopment ? devMenuItems.value : []),
  ...bottomMenuItems.value,
])

const flatItems = computed(() => flattenMenuItems(allItems.value))

// 选中项：优先精确匹配，再按路径边界匹配当前菜单。
const selectedKeys = computed(() => {
  const path = route.path
  const matched = flatItems.value
    .filter(hasMenuKey)
    .filter(item => {
      const key = String(item.key)
      return path === key || path.startsWith(`${key}/`)
    })
    .sort((left, right) => String(right.key).length - String(left.key).length)[0]
  return [matched?.key || '/home']
})

const onMenuClick: MenuProps['onClick'] = info => {
  const target = String(info.key)

  // 检查路由是否被锁定
  if (isRouteLocked.value) {
    // 如果路由被锁定，触发回调而不进行路由跳转
    triggerBlockCallback(target)
    return
  }

  if (
    import.meta.env.DEV &&
    target === '/update-download-dev' &&
    isDevelopment &&
    !router.hasRoute('UpdateDownloadDev')
  ) {
    router.addRoute({
      path: '/update-download-dev',
      name: 'UpdateDownloadDev',
      component: () => import('@/views/UpdateDownloadDev.vue'),
      meta: { title: t('comp.updateDownloadTest'), skipGuard: true },
    })
  }

  if (route.path !== target) router.push(target)
}
</script>

<style scoped>
.sider-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 10px 3px;
}

.sider-content :deep(.ant-menu) {
  border-inline-end: none !important;
  background: transparent !important;
}

/* 菜单项外框居中（左右留空），内容左对齐 */
.sider-content :deep(.ant-menu .ant-menu-item) {
  color: var(--ant-color-text);
  margin: 2px auto;
  /* 水平居中 */
  width: calc(100% - 16px);
  /* 两侧各留 8px 空隙 */
  border-radius: 6px;
  padding: 5px 16px !important;
  /* 左右内边距 */
  line-height: 36px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  /* 左对齐图标与文字 */
  gap: 6px;
  transition:
    background 0.16s ease,
    color 0.16s ease;
  text-align: left;
}

.sider-content :deep(.ant-menu .ant-menu-submenu) {
  width: calc(100% - 16px);
  margin: 2px auto;
  border-radius: 6px;
}

.sider-content :deep(.ant-menu .ant-menu-submenu-title) {
  height: 40px;
  margin: 0;
  padding: 5px 16px !important;
  line-height: 30px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text);
  transition:
    background 0.16s ease,
    color 0.16s ease;
}

.sider-content :deep(.ant-menu .ant-menu-submenu-title .anticon) {
  color: var(--ant-color-text-secondary);
  font-size: 18px;
}

.sider-content :deep(.ant-menu .ant-menu-submenu-title:hover) {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text);
}

.sider-content :deep(.ant-menu .ant-menu-submenu > .ant-menu) {
  background: transparent !important;
}

.sider-content :deep(.ant-menu .ant-menu-submenu .ant-menu-item) {
  width: calc(100% - 8px);
  margin: 2px 4px;
  padding-left: 40px !important;
  height: 36px;
  line-height: 32px;
}

.sider-content :deep(.ant-menu .ant-menu-item .anticon) {
  color: var(--ant-color-text-secondary);
  font-size: 18px;
  line-height: 1;
  transition: color 0.16s ease;
  margin-right: 0;
}

.sider-content :deep(.appearance-menu-icon) {
  width: 24px;
  height: 24px;
  object-fit: contain;
  flex: 0 0 24px;
}

.sider-content :deep(.appearance-menu-icon + .ant-menu-title-content) {
  margin-inline-start: 0 !important;
}

/* Hover */
.sider-content :deep(.ant-menu .ant-menu-item:hover) {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text);
}

.sider-content :deep(.ant-menu .ant-menu-item:hover .anticon) {
  color: var(--ant-color-text);
}

/* Selected */
.sider-content :deep(.ant-menu .ant-menu-item-selected) {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text) !important;
  font-weight: 500;
}

.sider-content :deep(.ant-menu .ant-menu-item-selected .anticon) {
  color: var(--ant-color-text-secondary);
}

.sider-content :deep(.ant-menu-light .ant-menu-item::after),
.sider-content :deep(.ant-menu-dark .ant-menu-item::after) {
  display: none;
}

/* 开发菜单区域 - 添加上边距以创建视觉分隔 */
.dev-menu {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border);
}

.bottom-menu {
  margin-top: auto;
}

.content-area {
  min-height: 0;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding: 32px;
}

.content-area::-webkit-scrollbar {
  display: none;
}
</style>

<!-- 使用标准 Sider 布局，去除 fixed 与 marginLeft，保持菜单样式与滚动行为 -->
