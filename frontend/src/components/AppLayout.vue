<template>
  <a-layout style="height: 100vh; overflow: hidden" class="app-layout-collapsed">
    <a-layout-sider
      v-model:collapsed="collapsed"
      collapsible
      :trigger="null"
      :width="180"
      :collapsed-width="60"
      :theme="isDark ? 'dark' : 'light'"
      style="height: 100vh; position: fixed; left: 0; top: 0; z-index: 100"
    >
      <div class="sider-content">
        <!-- Logo -->
        <div class="logo" @click="toggleCollapse">
          <img src="/src/assets/AUTO_MAA.ico" alt="AUTO_MAA" class="logo-image" />
          <span class="logo-text" :class="{ 'text-hidden': collapsed }">AUTO_MAA</span>
        </div>

        <!-- 主菜单容器 -->
        <div class="main-menu-container">
          <a-menu
            mode="inline"
            :inline-collapsed="collapsed"
            :theme="isDark ? 'dark' : 'light'"
            class="main-menu"
            v-model:selectedKeys="selectedKeys"
          >
            <template v-for="item in mainMenuItems" :key="item.path">
              <a-menu-item @click="goTo(item.path)" :data-title="item.label">
                <template #icon>
                  <component :is="item.icon" />
                </template>
                <span v-if="!collapsed" class="menu-text">{{ item.label }}</span>
              </a-menu-item>
            </template>
          </a-menu>
        </div>

        <!-- 底部菜单（带3px底部内边距） -->
        <a-menu
          mode="inline"
          :inline-collapsed="collapsed"
          :theme="isDark ? 'dark' : 'light'"
          class="bottom-menu"
          v-model:selectedKeys="selectedKeys"
        >
          <template v-for="item in bottomMenuItems" :key="item.path">
            <a-menu-item @click="goTo(item.path)" :data-title="item.label">
              <template #icon>
                <component :is="item.icon" />
              </template>
              <span v-if="!collapsed" class="menu-text">{{ item.label }}</span>
            </a-menu-item>
          </template>
        </a-menu>
      </div>
    </a-layout-sider>

    <!-- 主内容区 -->
    <a-layout
      :style="{
        marginLeft: collapsed ? '60px' : '180px',
        transition: 'margin-left 0.2s',
        height: '100vh',
      }"
    >
      <a-layout-content
        class="content-area"
        :style="{
          padding: '24px',
          background: isDark ? '#141414' : '#ffffff',
          height: '100vh',
          overflow: 'auto',
        }"
      >
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script lang="ts" setup>
import {
  HomeOutlined,
  FileTextOutlined,
  CalendarOutlined,
  UnorderedListOutlined,
  ControlOutlined,
  HistoryOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()

const collapsed = ref<boolean>(false)

// 菜单数据
const mainMenuItems = [
  { path: '/home', label: '主页', icon: HomeOutlined },
  { path: '/scripts', label: '脚本管理', icon: FileTextOutlined },
  { path: '/plans', label: '计划管理', icon: CalendarOutlined },
  { path: '/queue', label: '调度队列', icon: UnorderedListOutlined },
  { path: '/scheduler', label: '调度中心', icon: ControlOutlined },
  { path: '/history', label: '历史记录', icon: HistoryOutlined },
]

const bottomMenuItems = [{ path: '/settings', label: '设置', icon: SettingOutlined }]

// 自动同步选中项
const selectedKeys = computed(() => {
  const path = route.path
  const allItems = [...mainMenuItems, ...bottomMenuItems]
  const matched = allItems.find(item => path.startsWith(item.path))
  return [matched?.path || '/home']
})

const goTo = (path: string) => {
  router.push(path)
}

const toggleCollapse = () => {
  collapsed.value = !collapsed.value
}
</script>

<style scoped>
.sider-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding-bottom: 4px; /* 关键：添加3px底部内边距 */
}

/* Logo */
.logo {
  height: 42px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  margin: 4px;
  border-radius: 6px;
  cursor: pointer;
}

.logo:hover {
  background-color: rgba(255, 255, 255, 0.5);
}

:deep(.ant-layout-sider-light) .logo:hover {
  background-color: rgba(0, 0, 0, 0.04);
}

.logo-image {
  width: 32px;
  height: 32px;
}

.logo-text {
  margin-left: 12px;
  font-size: 16px;
  font-weight: bold;
  white-space: nowrap;
  opacity: 1;
  transition: opacity 0.2s ease;
}

.logo-text.text-hidden {
  opacity: 0;
}

/* 主菜单容器 */
.main-menu-container {
  flex: 1;
  overflow: auto;
  /* 修复滚动条显示问题 */
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.2) transparent;
}

.main-menu-container::-webkit-scrollbar {
  width: 6px;
}

.main-menu-container::-webkit-scrollbar-track {
  background: transparent;
}

.main-menu-container::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}

/* 底部菜单 */
.bottom-menu {
  margin-top: auto;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

:deep(.ant-layout-sider-light .bottom-menu) {
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}

/* 菜单项文字 */
.menu-text {
  margin-left: 36px;
  white-space: nowrap;
  opacity: 1;
  transition: opacity 0.2s ease;
}

/* 主题颜色 */
:deep(.ant-layout-sider-dark) .logo-text,
:deep(.ant-layout-sider-dark) .menu-text {
  color: #fff;
}

:deep(.ant-layout-sider-light) .logo-text,
:deep(.ant-layout-sider-light) .menu-text {
  color: rgba(0, 0, 0, 0.88);
}

/* 菜单项统一样式 */
:deep(.ant-menu-item),
:deep(.ant-menu-item-selected) {
  position: relative;
  height: 40px;
  line-height: 34px;
  margin: 0 6px;
  border-radius: 6px;
  padding: 0 !important;
}

/* 图标绝对定位 */
:deep(.ant-menu-item .ant-menu-item-icon) {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  pointer-events: none;
  z-index: 2;
}

/* 隐藏内容区滚动条 */
.content-area {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.content-area::-webkit-scrollbar {
  display: none;
}
</style>

<!-- 全局样式 -->
<style>
/* 收缩状态下，通过 data-title 显示 Tooltip */
.app-layout-collapsed .ant-menu-inline-collapsed .ant-menu-item:hover::before {
  content: attr(data-title);
  position: absolute;
  left: 60px;
  top: 50%;
  transform: translateY(-50%);
  background: #1890ff;
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
  font-size: 12px;
  z-index: 1000;
  opacity: 1;
  pointer-events: none;
}

/* 修复底部菜单在折叠状态下的tooltip位置 */
.app-layout-collapsed .ant-menu-inline-collapsed .bottom-menu .ant-menu-item:hover::before {
  left: 60px;
  transform: translateY(-50%);
}

/* 确保底部菜单在收缩状态下也有3px间距 */
.app-layout-collapsed .ant-menu-inline-collapsed .bottom-menu {
  padding-bottom: 6px;
}
</style>
