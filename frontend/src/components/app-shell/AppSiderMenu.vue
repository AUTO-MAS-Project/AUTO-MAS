<script setup lang="ts">
import { h } from 'vue'
import type { MenuProps } from 'ant-design-vue'
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
import type { PageDeclaration } from '@/router/pageDeclarations.ts'

defineProps<{
  items: PageDeclaration[]
  selectedKeys: string[]
  theme: 'light' | 'dark'
  sectionLabel?: string
  collapsed?: boolean
}>()

const emit = defineEmits<{
  (e: 'click', path: string): void
}>()

const icon = (Comp: any) => () => h(Comp)

const pageIconMap: Record<string, any> = {
  home: HomeOutlined,
  script: FileTextOutlined,
  plan: CalendarOutlined,
  emulator: DatabaseOutlined,
  plugin: ApiOutlined,
  market: AppstoreOutlined,
  queue: UnorderedListOutlined,
  scheduler: ControlOutlined,
  history: HistoryOutlined,
  tool: ToolOutlined,
  settings: SettingOutlined,
  dev: SettingOutlined,
  api: ApiOutlined,
  app: AppstoreOutlined,
}

const buildMenuItems = (pages: PageDeclaration[]) =>
  pages.map(page => ({
    key: page.path,
    label: page.menu_label,
    title: page.title,
    icon: icon(pageIconMap[page.icon] || AppstoreOutlined),
  }))

const handleClick: MenuProps['onClick'] = info => {
  emit('click', String(info.key))
}
</script>

<template>
  <nav
    class="app-sider-menu"
    :class="{ 'app-sider-menu--collapsed': collapsed }"
    :aria-label="sectionLabel || '主导航'"
  >
    <div v-if="sectionLabel" class="menu-section-label" :aria-hidden="collapsed">
      {{ sectionLabel }}
    </div>
    <a-menu
      :selected-keys="selectedKeys"
      mode="inline"
      :theme="theme"
      :items="buildMenuItems(items)"
      :inline-collapsed="collapsed"
      @click="handleClick"
    />
  </nav>
</template>

<style scoped>
/*
 * 折叠动画布局稳定性契约（与 AppSider / GlobalSearch 同构）：
 * 行高固定 40px；图标固定 20px 列居中（18px 字形）；两态 padding 相同（0 10px）、
 * 外框公式相同（calc(100% - 8px) 水平居中）→ 图标 x 位置全程不漂移；
 * 文字以 max-width/opacity/transform 收缩隐藏；纵向属性不参与 transition。
 */
.app-sider-menu {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* 分组标题两态保持同一固定行高，仅以 opacity/transform 隐藏，杜绝纵向回流 */
.menu-section-label {
  height: 32px;
  display: flex;
  align-items: center;
  overflow: hidden;
  opacity: 1;
  padding: 0 var(--v6-space-4);
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
  letter-spacing: 0.02em;
  font-weight: var(--v6-font-weight-semibold);
  white-space: nowrap;
  transform: translateX(0);
  transition:
    opacity var(--v6-motion-fast) var(--v6-ease-out),
    transform var(--v6-motion-base) var(--v6-ease-out);
}

.app-sider-menu :deep(.ant-menu) {
  border-inline-end: none !important;
  background: transparent !important;
}

.app-sider-menu :deep(.ant-menu .ant-menu-item) {
  color: var(--ant-color-text);
  margin: 2px auto;
  width: calc(100% - 8px);
  border-radius: 6px;
  padding: 0 10px !important;
  line-height: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  overflow: hidden;
  transition:
    background var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
  text-align: left;
  user-select: none;
  -webkit-user-select: none;
}

/* 图标固定列宽：两态图标 x 位置不漂移 */
.app-sider-menu :deep(.ant-menu .ant-menu-item .anticon) {
  flex: 0 0 20px;
  width: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-secondary);
  font-size: 18px;
  line-height: 1;
  transition: color 0.16s ease;
  margin-right: 0;
}

.app-sider-menu :deep(.ant-menu .ant-menu-item:hover) {
  background: var(--v6-vibrancy-hover);
  color: var(--ant-color-text);
}

.app-sider-menu :deep(.ant-menu .ant-menu-item:hover .anticon) {
  color: var(--ant-color-text);
}

.app-sider-menu :deep(.ant-menu .ant-menu-item-selected) {
  background: var(--v6-vibrancy-active) !important;
  color: #fff !important;
  font-weight: 500;
}

.app-sider-menu :deep(.ant-menu .ant-menu-item-selected .anticon) {
  color: #fff !important;
}

.app-sider-menu :deep(.ant-menu .ant-menu-item-selected .ant-menu-title-content) {
  color: #fff !important;
}

.app-sider-menu :deep(.ant-menu .ant-menu-item:focus-visible) {
  outline: none;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v6-color-info) 56%, transparent);
  border-radius: var(--v6-radius-control);
}

.app-sider-menu :deep(.ant-menu .ant-menu-title-content) {
  display: block;
  max-width: 160px;
  overflow: hidden;
  opacity: 1;
  white-space: nowrap;
  transform: translateX(0);
  transition:
    max-width var(--v6-motion-base) var(--v6-ease-out),
    opacity var(--v6-motion-fast) var(--v6-ease-out),
    transform var(--v6-motion-base) var(--v6-ease-out);
}

/* 折叠态只隐藏文字：行几何（高/宽公式/内边距/图标列）与展开态完全一致 */
.app-sider-menu--collapsed .menu-section-label {
  opacity: 0;
  pointer-events: none;
  transform: translateX(-8px);
}

.app-sider-menu--collapsed :deep(.ant-menu-inline-collapsed) {
  width: 100%;
}

.app-sider-menu--collapsed :deep(.ant-menu .ant-menu-title-content) {
  width: 0;
  max-width: 0;
  margin-inline: 0 !important;
  opacity: 0;
  pointer-events: none;
  transform: translateX(-8px);
}

.app-sider-menu--collapsed :deep(.ant-menu .ant-menu-item .anticon),
.app-sider-menu--collapsed :deep(.ant-menu .ant-menu-item .ant-menu-item-icon) {
  margin: 0;
}

.app-sider-menu :deep(.ant-menu-light .ant-menu-item::after),
.app-sider-menu :deep(.ant-menu-dark .ant-menu-item::after) {
  display: none;
}

@media (prefers-reduced-motion: reduce) {
  .app-sider-menu :deep(.ant-menu .ant-menu-item) {
    transition: none;
  }

  .app-sider-menu :deep(.ant-menu .ant-menu-item .anticon) {
    transition: none;
  }

  .menu-section-label,
  .app-sider-menu :deep(.ant-menu .ant-menu-title-content) {
    transition: none;
  }
}

:global(:root[data-perf-mode='low']) .menu-section-label,
:global(:root[data-perf-mode='low']) .app-sider-menu :deep(.ant-menu .ant-menu-item),
:global(:root[data-perf-mode='low']) .app-sider-menu :deep(.ant-menu .ant-menu-title-content) {
  transition: none;
}
</style>
