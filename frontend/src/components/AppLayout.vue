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
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          v-model:selectedKeys="selectedKeys"
          :items="mainMenuItems"
          @click="onMenuClick"
        />
        <a-menu
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          class="bottom-menu"
          v-model:selectedKeys="selectedKeys"
          :items="bottomMenuItems"
          @click="onMenuClick"
        />
      </div>
    </a-layout-sider>

    <a-layout style="flex: 1; min-width: 0">
      <a-layout-content class="content-area">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script lang="ts" setup>
import {
  CalendarOutlined,
  ControlOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HistoryOutlined,
  HomeOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import { computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'
import { useRouteLock } from '../composables/useRouteLock.ts'
import type { MenuProps } from 'ant-design-vue'

const SIDER_WIDTH = 160

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()

// 工具：生成菜单项
const icon = (Comp: any) => () => h(Comp)

const mainMenuItems = [
  { key: '/home', label: '主页', icon: icon(HomeOutlined) },
  { key: '/scripts', label: '脚本管理', icon: icon(FileTextOutlined) },
  { key: '/plans', label: '计划管理', icon: icon(CalendarOutlined) },
  { key: '/emulators', label: '模拟器管理', icon: icon(DatabaseOutlined) },
  { key: '/queue', label: '调度队列', icon: icon(UnorderedListOutlined) },
  { key: '/scheduler', label: '调度中心', icon: icon(ControlOutlined) },
]
const bottomMenuItems = [
  { key: '/history', label: '历史记录', icon: icon(HistoryOutlined) },
  { key: '/settings', label: '设置', icon: icon(SettingOutlined) },
]

const allItems = [...mainMenuItems, ...bottomMenuItems]

// 选中项：根据当前路径前缀匹配
const selectedKeys = computed(() => {
  const path = route.path
  const matched = allItems.find(i => path.startsWith(String(i.key)))
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
  margin: 2px auto; /* 水平居中 */
  width: calc(100% - 16px); /* 两侧各留 8px 空隙 */
  border-radius: 6px;
  padding: 5px 16px !important; /* 左右内边距 */
  line-height: 36px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: flex-start; /* 左对齐图标与文字 */
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
