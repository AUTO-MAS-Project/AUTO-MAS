<template>
  <a-layout style="height: 100vh; overflow: hidden">
    <a-layout-sider
      v-model:collapsed="collapsed"
      :trigger="null"
      collapsible
      :theme="isDark ? 'dark' : 'light'"
      style="height: 100vh; position: fixed; left: 0; top: 0; z-index: 100"
      :width="180"
      :collapsed-width="60"
    >
      <div class="sider-content">
        <!-- Logo区域 - 点击切换展开/折叠 -->
        <div class="logo" @click="collapsed = !collapsed">
          <img src="/AUTO_MAA.ico" alt="AUTO MAA" class="logo-image" />
          <div v-if="!collapsed" class="logo-text">AUTO_MAA</div>
        </div>

        <!-- 主菜单 -->
        <div class="main-menu">
          <a-menu
            v-model:selectedKeys="selectedKeys"
            :theme="isDark ? 'dark' : 'light'"
            mode="inline"
            :inline-collapsed="collapsed"
          >
            <a-menu-item key="/home" @click="handleMenuClick('/home')">
              <home-outlined />
              <span>主页</span>
            </a-menu-item>
            <a-menu-item key="/scripts" @click="handleMenuClick('/scripts')">
              <file-text-outlined />
              <span>脚本管理</span>
            </a-menu-item>
            <a-menu-item key="/plans" @click="handleMenuClick('/plans')">
              <calendar-outlined />
              <span>计划管理</span>
            </a-menu-item>
            <a-menu-item key="/queue" @click="handleMenuClick('/queue')">
              <unordered-list-outlined />
              <span>调度队列</span>
            </a-menu-item>
            <a-menu-item key="/scheduler" @click="handleMenuClick('/scheduler')">
              <control-outlined />
              <span>调度中心</span>
            </a-menu-item>
            <a-menu-item key="/history" @click="handleMenuClick('/history')">
              <history-outlined />
              <span>历史记录</span>
            </a-menu-item>
          </a-menu>
        </div>

        <!-- 底部设置菜单 -->
        <div class="bottom-menu">
          <a-menu
            v-model:selectedKeys="selectedKeys"
            :theme="isDark ? 'dark' : 'light'"
            mode="inline"
            :inline-collapsed="collapsed"
          >
            <a-menu-item key="/settings" @click="handleMenuClick('/settings')">
              <setting-outlined />
              <span>设置</span>
            </a-menu-item>
          </a-menu>
        </div>
      </div>
    </a-layout-sider>

    <a-layout
      :style="{
        marginLeft: collapsed ? '60px' : '180px',
        height: '100vh',
        transition: 'margin-left 0.2s',
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
const selectedKeys = ref<string[]>([route.path])

// 监听路由变化更新选中状态
const currentRoute = computed(() => route.path)
selectedKeys.value = [currentRoute.value]

const handleMenuClick = (path: string) => {
  router.push(path)
  selectedKeys.value = [path]
}
</script>

<style scoped>
.sider-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px;
  margin: 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.logo:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.logo-image {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.logo-text {
  font-size: 16px;
  font-weight: bold;
  letter-spacing: 1px;
}

/* 浅色模式下的 Logo 悬停效果 */
:deep(.ant-layout-sider-light) .logo:hover {
  background-color: rgba(0, 0, 0, 0.04);
}

.main-menu {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 60px;
  /* 为底部设置菜单留出空间 */
}

.bottom-menu {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: inherit;
}

/* 深色模式下的底部菜单边框 */
:deep(.ant-layout-sider-dark) .bottom-menu {
  /*
  border-top: 1px solid rgba(255, 255, 255, 0.1);
   */
}

/* 浅色模式下的底部菜单边框 */
:deep(.ant-layout-sider-light) .bottom-menu {
  /*
  border-top: 1px solid #d9d9d9;

   */
}

/* 深色模式样式 */
:deep(.ant-layout-sider-dark) .logo-text {
  color: white;
}

/* 浅色模式样式 */
:deep(.ant-layout-sider-light) .logo-text {
  color: rgba(0, 0, 0, 0.88);
}

/* 浅色模式下的侧边栏背景色 */
:deep(.ant-layout-sider-light) {
  background: #f5f5f5 !important;
}

/* 浅色模式下的菜单背景色 */
:deep(.ant-layout-sider-light .ant-menu-light) {
  background: #f5f5f5 !important;
}

:deep(.ant-layout-sider) {
  position: relative;
}

/* 移除菜单右边框 */
:deep(.ant-menu) {
  border-right: none !important;
  border-inline-end: none !important;
}

/* 更强制地移除菜单右边框 */
:deep(.ant-menu-light.ant-menu-root.ant-menu-inline),
:deep(.ant-menu-light.ant-menu-root.ant-menu-vertical),
:deep(.ant-menu-dark.ant-menu-root.ant-menu-inline),
:deep(.ant-menu-dark.ant-menu-root.ant-menu-vertical) {
  border-inline-end: none !important;
  border-right: none !important;
}

/* 确保折叠时图标显示 */
:deep(.ant-menu-inline-collapsed .ant-menu-item) {
  padding: 0 calc(50% - 14px);
}

:deep(.ant-menu-inline-collapsed .ant-menu-item .anticon) {
  font-size: 16px;
  line-height: 40px;
}

/* 隐藏内容区域滚动条 */
.content-area {
  /* Webkit 浏览器 (Chrome, Safari, Edge) */
  scrollbar-width: none;
  /* Firefox */
  -ms-overflow-style: none;
}

.content-area::-webkit-scrollbar {
  display: none;
}

/* 隐藏侧边栏主菜单滚动条 */
.main-menu {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.main-menu::-webkit-scrollbar {
  display: none;
}
</style>
