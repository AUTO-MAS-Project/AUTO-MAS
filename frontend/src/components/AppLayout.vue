<template>
  <a-layout style="flex: 1; min-height: 0; overflow: hidden">
    <a-layout-sider
      :width="SIDER_WIDTH"
      :theme="isDark ? 'dark' : 'light'"
      :style="{
        background: 'var(--ant-color-bg-elevated)',
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

    <a-layout style="flex: 1; min-width: 0">
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
  ToolOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import { computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'
import { useRouteLock } from '../composables/useRouteLock.ts'
import type { MenuProps } from 'ant-design-vue'

const { t } = useI18n()

const SIDER_WIDTH = 160

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()

// 工具：生成菜单项
const icon = (Comp: any) => () => h(Comp)

// 判断是否为开发环境。必须与 router/index.ts 里注册调试路由的条件保持一致，
// 否则菜单项会指向未注册的路由。之前这里还额外判断了 hostname === 'localhost'，
// 生产环境走 loadFile（file:// 协议，hostname 为空）不会命中，但用 vite preview
// 预览生产构建时会命中，导致菜单显示了实际不存在的路由。
const isDevelopment = computed(() => import.meta.env.DEV)

const mainMenuItems = computed(() => [
  { key: '/home', label: t('comp.home'), icon: icon(HomeOutlined) },
  { key: '/scripts', label: t('comp.scripts'), icon: icon(FileTextOutlined) },
  { key: '/plans', label: t('comp.plans'), icon: icon(CalendarOutlined) },
  { key: '/emulators', label: t('comp.emulators'), icon: icon(DatabaseOutlined) },
  { key: '/queue', label: t('comp.queue'), icon: icon(UnorderedListOutlined) },
  { key: '/scheduler', label: t('comp.scheduler'), icon: icon(ControlOutlined) },
])

// 开发环境专用菜单项
const devMenuItems = computed(() => [
  { key: '/TestRouter', label: t('comp.testRoute'), icon: icon(SettingOutlined) },
  { key: '/OCRdev', label: t('comp.ocrTest'), icon: icon(SettingOutlined) },
  { key: '/OverlayMaskDev', label: t('comp.overlayEasterEggTest'), icon: icon(SettingOutlined) },
  ...(import.meta.env.DEV
    ? [
        {
          key: '/update-download-dev',
          label: t('comp.updateDownloadTest'),
          icon: icon(BugOutlined),
        },
      ]
    : []),
])

const bottomMenuItems = computed(() => [
  { key: '/gamesign', label: t('comp.checkIns'), icon: icon(CarryOutOutlined) },
  { key: '/history', label: t('comp.history'), icon: icon(HistoryOutlined) },
  { key: '/tools', label: t('comp.tools'), icon: icon(ToolOutlined) },
  { key: '/settings', label: t('comp.settings'), icon: icon(SettingOutlined) },
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
  ...(isDevelopment.value ? devMenuItems.value : []),
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
    target === '/update-download-dev' &&
    import.meta.env.DEV &&
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
