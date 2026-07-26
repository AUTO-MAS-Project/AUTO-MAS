<template>
  <div class="game-emulator-center">
    <!-- 统一 MacPageHeader 规范（compact + transparent，分段切换在右侧） -->
    <MacPageHeader
      class="center-page-header"
      title="游戏与模拟器"
      subtitle="统一管理游戏实例、启动方式、模拟器配置与设备连接"
      compact
      transparent
    >
      <a-segmented
        v-model:value="activeTab"
        class="center-segmented"
        :options="tabOptions"
        @change="onTabChange"
      />
    </MacPageHeader>

    <main class="center-content">
      <GameInstancesTab v-if="activeTab === 'games'" />
      <EmulatorTab v-else />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import GameInstancesTab from './GameInstancesTab.vue'
import EmulatorTab from './EmulatorTab.vue'
import MacPageHeader from '@/components/mac/PageHeader.vue'

const route = useRoute()
type CenterTab = 'games' | 'emulators'

const activeTab = ref<CenterTab>('games')
const tabOptions = [
  { label: '游戏实例', value: 'games' },
  { label: '模拟器与连接', value: 'emulators' },
]

const TAB_STORAGE_KEY = 'game_center_active_tab'
const isCenterTab = (value: unknown): value is CenterTab =>
  value === 'games' || value === 'emulators'

const onTabChange = (value: string | number) => {
  if (!isCenterTab(value)) return
  activeTab.value = value
  localStorage.setItem(TAB_STORAGE_KEY, value)
}

onMounted(() => {
  const savedTab = localStorage.getItem(TAB_STORAGE_KEY)
  if (isCenterTab(savedTab)) activeTab.value = savedTab
  if (isCenterTab(route.query.tab)) activeTab.value = route.query.tab
})

watch(
  () => route.query.tab,
  value => {
    if (isCenterTab(value)) activeTab.value = value
  }
)
</script>

<style scoped>
.game-emulator-center {
  height: 100%;
  min-height: 0;
  min-width: 0;
  container: game-emulator / inline-size;
  padding: var(--v6-space-4) var(--v6-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
  background: transparent;
}

/* 页面容器自带内边距，抵消 PageHeader 的全宽内边距保持对齐 */
.center-page-header {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.center-page-header :deep(.mac-page-header) {
  padding-inline: 0;
}

.center-segmented {
  flex: 0 0 auto;
  padding: 3px;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: 10px;
  background: color-mix(in srgb, var(--v6-color-fill-tertiary) 72%, transparent);
}

.center-segmented :deep(.ant-segmented-item) {
  min-height: 30px;
  padding-inline: 12px;
  border-radius: 8px;
  color: var(--v6-color-text-secondary);
  font-size: 13px;
}

.center-segmented :deep(.ant-segmented-item-selected) {
  color: var(--v6-color-text);
  background: color-mix(in srgb, var(--v6-color-surface) 92%, transparent);
  box-shadow: var(--v6-shadow-sm);
}

.center-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.center-content > * {
  height: 100%;
}

/* .game-emulator-center 自身规则须由外层 app-shell 的 app-content 容器驱动
   (@container 不能命中声明容器的元素自身) */
@container app-content (max-width: 760px) {
  .game-emulator-center {
    padding: var(--v6-space-3);
  }
}

/* 页头窄屏换行由 MacPageHeader 内置容器查询处理 */
@container game-emulator (max-width: 760px) {
  .center-segmented {
    width: 100%;
  }
}
</style>
