<template>
  <a-layout style="height: 100vh; overflow: hidden">
    <a-layout-sider
      :width="siderWidth"
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

    <a-layout :style="{ marginLeft: siderWidth + 'px', height: 'calc(100vh - 32px)', transition: 'margin-left .2s' }">
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
import { computed, h, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'
import type { MenuProps } from 'ant-design-vue'

// 动态侧栏宽度：窗口宽度的30%，限制 120 - 200 像素
const MIN_SIDER_WIDTH = 120
const MAX_SIDER_WIDTH = 220
const WIDTH_PERCENT = 0.2
const siderWidth = ref<number>(150)

const calcSiderWidth = () => {
  const w = window.innerWidth
  return Math.min(MAX_SIDER_WIDTH, Math.max(MIN_SIDER_WIDTH, Math.round(w * WIDTH_PERCENT)))
}

const handleResize = () => {
  siderWidth.value = calcSiderWidth()
}

onMounted(() => {
  siderWidth.value = calcSiderWidth()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()

// 工具：生成菜单项（图标与文字放入同一容器）
const makeMenuItem = (key: string, text: string, IconComp: any) => ({
  key,
  label: h('div', { class: 'menu-item-center' }, [ h(IconComp), h('span', text) ])
})

const mainMenuItems = [
  makeMenuItem('/home', '主页', HomeOutlined),
  makeMenuItem('/scripts', '脚本管理', FileTextOutlined),
  makeMenuItem('/plans', '计划管理', CalendarOutlined),
  makeMenuItem('/queue', '调度队列', UnorderedListOutlined),
  makeMenuItem('/scheduler', '调度中心', ControlOutlined),
  makeMenuItem('/history', '历史记录', HistoryOutlined),
]
const bottomMenuItems = [
  makeMenuItem('/settings', '设置', SettingOutlined),
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
  color: var(--app-menu-text-color, #333);
  margin: 2px auto;               /* 水平居中 */
  width: calc(100% - 16px);       /* 两侧各留 8px 空隙 */
  border-radius: 6px;
  padding: 0 6px !important;     /* 组合居中后可稍微缩减左右内边距 */
  line-height: 36px;
  height: 36px;
  font-size: 16px; /* 提高字体大小 */
  display: flex;
  align-items: center;
  justify-content: center;       /* 改为居中 */
  text-align: center;            /* 文本居中 */
  gap: 6px;
  transition: background .16s ease, color .16s ease;
}
/* 图标样式 */
.sider-content :deep(.ant-menu .ant-menu-item .anticon) {
  color: var(--app-menu-icon-color, #666);
  font-size: 16px;
  line-height: 1;
  transition: color .16s ease;
  margin-right: 0;
}
/* Hover */
.sider-content :deep(.ant-menu .ant-menu-item:hover) {
  background: var(--app-menu-item-hover-bg, rgba(0,0,0,0.04));
  color: var(--app-menu-item-hover-text-color, #1677ff);
}
.sider-content :deep(.ant-menu .ant-menu-item:hover .anticon) { color: var(--app-menu-item-hover-text-color, #1677ff); }
/* Selected */
.sider-content :deep(.ant-menu .ant-menu-item-selected) {
  background: var(--app-menu-item-selected-bg, rgba(22,119,255,0.15));
  color: var(--app-menu-text-color, #1677ff) !important;
  font-weight: 500;
}
.sider-content :deep(.ant-menu .ant-menu-item-selected .anticon) { color: var(--app-menu-icon-color, #1677ff); }
.sider-content :deep(.ant-menu-light .ant-menu-item::after),
.sider-content :deep(.ant-menu-dark .ant-menu-item::after) { display: none; }
.bottom-menu { margin-top:auto; }
.content-area { height:100%; overflow:auto; scrollbar-width:none; -ms-overflow-style:none; }
.content-area::-webkit-scrollbar { display:none; }
.sider-content :deep(.menu-item-center){
  display:flex;
  align-items:center;
  justify-content:center;
  width:100%;
  gap:6px;
}
.sider-content :deep(.menu-item-center > .anticon){
  font-size:18px;
}
</style>

<!-- 菜单项图标与文字已居中 -->
