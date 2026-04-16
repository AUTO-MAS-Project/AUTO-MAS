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
        <router-view v-slot="{ Component, route }">
          <keep-alive :include="['Scheduler']">
            <component :is="Component" :key="route.path" />
          </keep-alive>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script lang="ts" setup>
import {
  ApiOutlined,
  AppstoreOutlined,
  CalendarOutlined,
  ControlOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HistoryOutlined,
  HomeOutlined,
  SettingOutlined,
  ToolOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import type { MenuProps } from 'ant-design-vue'
import { computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useRouteLock } from '../composables/useRouteLock.ts'
import { useTheme } from '../composables/useTheme.ts'

const SIDER_WIDTH = 160

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()

const icon = (Comp: any) => () => h(Comp)

const isDevelopment = computed(() => {
  return (
    process.env.NODE_ENV === 'development' ||
    (import.meta as any).env?.DEV === true ||
    window.location.hostname === 'localhost'
  )
})

const mainMenuItems = [
  { key: '/home', label: '主页', icon: icon(HomeOutlined) },
  { key: '/scripts', label: '脚本管理', icon: icon(FileTextOutlined) },
  { key: '/plans', label: '计划管理', icon: icon(CalendarOutlined) },
  { key: '/emulators', label: '模拟器管理', icon: icon(DatabaseOutlined) },
  { key: '/queue', label: '调度队列', icon: icon(UnorderedListOutlined) },
  { key: '/scheduler', label: '调度中心', icon: icon(ControlOutlined) },
]

const devMenuItems = [
  { key: '/TestRouter', label: '测试路由', icon: icon(SettingOutlined) },
  { key: '/OCRdev', label: 'OCR 测试', icon: icon(SettingOutlined) },
  { key: '/WSdev', label: 'WebSocket 测试', icon: icon(ApiOutlined) },
  { key: '/OverlayMaskDev', label: '遮罩彩蛋测试', icon: icon(SettingOutlined) },
]

const bottomMenuItems = [
  { key: '/history', label: '历史记录', icon: icon(HistoryOutlined) },
  { key: '/tools', label: '工具', icon: icon(ToolOutlined) },
  { key: '/plugins', label: '插件管理', icon: icon(AppstoreOutlined) },
  { key: '/settings', label: '设置', icon: icon(SettingOutlined) },
]

const allItems = computed(() => [
  ...mainMenuItems,
  ...(isDevelopment.value ? devMenuItems : []),
  ...bottomMenuItems,
])

const selectedKeys = computed(() => {
  const path = route.path
  const matched = allItems.value.find(item => path.startsWith(String(item.key)))
  return [matched?.key || '/home']
})

const onMenuClick: MenuProps['onClick'] = info => {
  const target = String(info.key)

  if (isRouteLocked.value) {
    triggerBlockCallback(target)
    return
  }

  if (route.path !== target) {
    router.push(target)
  }
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

.sider-content :deep(.ant-menu .ant-menu-item) {
  color: var(--ant-color-text);
  margin: 2px auto;
  width: calc(100% - 16px);
  border-radius: 6px;
  padding: 5px 16px !important;
  line-height: 36px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  transition:
    background 0.16s ease,
    color 0.16s ease;
  text-align: left;
}

.sider-content :deep(.ant-menu .ant-menu-item .anticon) {
  color: var(--ant-color-text-secondary);
  font-size: 18px;
  line-height: 1;
  transition: color 0.16s ease;
  margin-right: 0;
}

.sider-content :deep(.ant-menu .ant-menu-item:hover) {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text);
}

.sider-content :deep(.ant-menu .ant-menu-item:hover .anticon) {
  color: var(--ant-color-text);
}

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
