<template>
  <a-layout style="height: 100vh; overflow: hidden">
    <a-layout-sider
      :width="SIDER_WIDTH"
      :theme="isDark ? 'dark' : 'light'"
      :style="{ height: 'calc(100vh - 32px)', position: 'fixed', left: '0', top: '32px', zIndex: 100, background: 'var(--app-sider-bg)', borderRight: '1px solid var(--app-sider-border-color)' }"
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

    <a-layout :style="{ marginLeft: SIDER_WIDTH + 'px', height: 'calc(100vh - 32px)', transition: 'margin-left .2s' }">
      <a-layout-content class="content-area">
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
import { computed, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'
import type { MenuProps } from 'ant-design-vue'

const SIDER_WIDTH = 140

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()

// 工具：生成菜单项
const icon = (Comp: any) => () => h(Comp)

const mainMenuItems = [
  { key: '/home', label: '主页', icon: icon(HomeOutlined) },
  { key: '/scripts', label: '脚本管理', icon: icon(FileTextOutlined) },
  { key: '/plans', label: '计划管理', icon: icon(CalendarOutlined) },
  { key: '/queue', label: '调度队列', icon: icon(UnorderedListOutlined) },
  { key: '/scheduler', label: '调度中心', icon: icon(ControlOutlined) },
  { key: '/history', label: '历史记录', icon: icon(HistoryOutlined) },
]
const bottomMenuItems = [
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
  if (route.path !== target) router.push(target)
}
</script>

<style scoped>
.sider-content { height:100%; display:flex; flex-direction:column; padding:4px 0 8px 0; }
.sider-content :deep(.ant-menu) { border-inline-end: none !important; background: transparent !important; }
/* 菜单项外框居中（左右留空），内容左对齐 */
.sider-content :deep(.ant-menu .ant-menu-item) {
  color: var(--app-menu-text-color);
  margin: 2px auto;               /* 水平居中 */
  width: calc(100% - 16px);       /* 两侧各留 8px 空隙 */
  border-radius: 6px;
  padding: 0 10px !important;     /* 左右内边距 */
  line-height: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: flex-start;    /* 左对齐图标与文字 */
  gap: 6px;
  transition: background .16s ease, color .16s ease;
  text-align: left;
}
.sider-content :deep(.ant-menu .ant-menu-item .anticon) {
  color: var(--app-menu-icon-color);
  font-size: 16px;
  line-height: 1;
  transition: color .16s ease;
  margin-right: 0;
}
/* Hover */
.sider-content :deep(.ant-menu .ant-menu-item:hover) {
  background: var(--app-menu-item-hover-bg, var(--app-menu-item-hover-bg-hex));
  color: var(--app-menu-item-hover-text-color);
}
.sider-content :deep(.ant-menu .ant-menu-item:hover .anticon) { color: var(--app-menu-item-hover-text-color); }
/* Selected */
.sider-content :deep(.ant-menu .ant-menu-item-selected) {
  background: var(--app-menu-item-selected-bg, var(--app-menu-item-selected-bg-hex));
  color: var(--app-menu-text-color) !important;
  font-weight: 500;
}
.sider-content :deep(.ant-menu .ant-menu-item-selected .anticon) { color: var(--app-menu-icon-color); }
.sider-content :deep(.ant-menu-light .ant-menu-item::after),
.sider-content :deep(.ant-menu-dark .ant-menu-item::after) { display: none; }
.bottom-menu { margin-top:auto; }
.content-area { height:100%; overflow:auto; scrollbar-width:none; -ms-overflow-style:none; }
.content-area::-webkit-scrollbar { display:none; }
</style>

<!-- 调整：外框（菜单项背景块）水平居中，文字与图标左对齐 -->
