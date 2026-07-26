<template>
  <div class="home-page">
    <div class="home-header">
      <div class="home-heading-copy">
        <p class="home-dynamic-copy">
          <span>{{ greeting }}</span>
        </p>
      </div>

      <div class="header-actions">
        <HomeQuickActionsCard @navigate="navigateTo" />
        <a-button
          :type="layoutEditing ? 'primary' : 'default'"
          class="layout-edit-button"
          @click="toggleLayoutEditing"
        >
          <template #icon>
            <CheckOutlined v-if="layoutEditing" />
            <EditOutlined v-else />
          </template>
          {{ layoutEditing ? '完成' : '编辑布局' }}
        </a-button>
        <!-- 工具行按钮统一默认态样式；公告如需强调未读，用小红点 badge 而非整钮变色 -->
        <a-button :loading="noticeLoading" class="notice-button" @click="showNotice">
          <template #icon>
            <BellOutlined />
          </template>
          查看公告
        </a-button>
        <a-button
          class="refresh-button"
          :loading="loading"
          :disabled="startingHomeTask"
          @click="refresh"
        >
          <template #icon>
            <ReloadOutlined />
          </template>
          刷新
        </a-button>
      </div>
    </div>

    <NoticeModal
      v-model:visible="noticeVisible"
      :notice-data="noticeData"
      @confirmed="onNoticeConfirmed"
    />

    <a-alert
      v-if="homeDataError"
      class="home-data-error"
      type="warning"
      show-icon
      :message="homeDataError"
    >
      <template #action>
        <a-button size="small" :loading="loading" @click="refresh">重新加载</a-button>
      </template>
    </a-alert>

    <!-- 快速开始固定置顶，不参与拖拽排序 -->
    <section
      v-if="isHomeModuleVisible('command')"
      class="home-module home-module--command"
      :class="{
        'is-editing': layoutEditing,
        'is-hidden': layoutEditing && !isHomeModuleShown('command'),
      }"
      :aria-label="moduleTitleMap.command"
    >
      <HomeModuleEditor
        v-if="layoutEditing"
        :title="moduleTitleMap.command"
        :is-shown="isHomeModuleShown('command')"
        :can-move-up="false"
        :can-move-down="false"
        @toggle-shown="setHomeModuleShown('command', $event)"
      />

      <HomeCommandCard
        v-model:selected-task-id="selectedHomeTaskId"
        v-model:selected-mode="selectedHomeMode"
        :command-title="commandTitle"
        :bootstrapping="isBootstrapping"
        :task-options="schedulerTaskOptions"
        :mode-options="schedulerModeOptions"
        :tasks-loading="schedulerTasksLoading"
        :tasks-error="schedulerTasksError"
        :starting="startingHomeTask"
        :start-error="homeTaskStartError"
        @dropdown-visible-change="onSchedulerDropdownVisibleChange"
        @retry-start="retryHomeTask"
        @start="startHomeTask"
      />
    </section>

    <!-- 其余模块：编辑布局时可拖拽排列（安卓小组件式），DOM 顺序即视觉顺序 -->
    <draggable
      v-model="reorderableHomeModules"
      class="home-content"
      tag="div"
      :item-key="moduleItemKey"
      :animation="160"
      :disabled="!layoutEditing"
      handle=".module-editor-bar"
      ghost-class="home-module-ghost"
      chosen-class="home-module-chosen"
      drag-class="home-module-drag"
    >
      <template #item="{ element: moduleKey }">
        <section
          v-show="isHomeModuleVisible(moduleKey)"
          class="home-module"
          :class="[
            `home-module--${moduleKey}`,
            {
              'is-editing': layoutEditing,
              'is-hidden': layoutEditing && !isHomeModuleShown(moduleKey),
            },
          ]"
          :aria-label="moduleTitle(moduleKey)"
        >
          <HomeModuleEditor
            v-if="layoutEditing"
            :title="moduleTitle(moduleKey)"
            :is-shown="isHomeModuleShown(moduleKey)"
            :can-move-up="canMoveHomeModule(moduleKey, 'up')"
            :can-move-down="canMoveHomeModule(moduleKey, 'down')"
            @toggle-shown="setHomeModuleShown(moduleKey, $event)"
            @move="moveHomeModule(moduleKey, $event)"
          />

          <HomeStatusCard
            v-if="moduleKey === 'status'"
            :ws-status="wsStatus"
            :backend-status="backendStatus"
            :is-ready="statusSummary.isReady"
            :has-errors="statusSummary.hasErrors"
            :queued-tasks="queueSummary?.itemCount ?? 0"
            :recent-results="recentRecords.length"
          />

          <HomeRecentCard
            v-else-if="moduleKey === 'recent'"
            :records="recentRecords"
            :loading="loading"
            @navigate="navigateTo"
          />

          <HomeQueueCard
            v-else-if="moduleKey === 'queue'"
            :summary="queueSummary"
            :loading="loading"
            @navigate="navigateTo"
          />

          <div v-else-if="moduleKey === 'satellite'" class="satellite-card">
            <div class="satellite-card__header">
              <h2>卫星视图</h2>
              <span class="satellite-card__live"><i aria-hidden="true" />实时</span>
            </div>
            <SatelliteAnimation />
          </div>

          <HomeProxyCard
            v-else-if="moduleKey === 'proxy'"
            :proxy-data="proxyData"
            :loading="loading"
            :format-proxy-display="formatProxyDisplay"
          />
        </section>
      </template>
    </draggable>
  </div>
</template>

<script setup lang="ts">
import { BellOutlined, CheckOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import NoticeModal from '@/components/NoticeModal.vue'
import SatelliteAnimation from '@/components/SatelliteAnimation.vue'
import { useHomeLogic, moduleTitleMap, type HomeModuleKey } from '@/views/home/useHomeLogic'
import { navigateTo } from '@/router'
import HomeStatusCard from './home/components/HomeStatusCard.vue'
import HomeCommandCard from './home/components/HomeCommandCard.vue'
import HomeRecentCard from './home/components/HomeRecentCard.vue'
import HomeQueueCard from './home/components/HomeQueueCard.vue'
import HomeQuickActionsCard from './home/components/HomeQuickActionsCard.vue'
import HomeProxyCard from './home/components/HomeProxyCard.vue'
import HomeModuleEditor from './home/components/HomeModuleEditor.vue'

defineOptions({
  name: 'HomeView',
})

const {
  loading,
  homeDataError,
  schedulerTasksLoading,
  startingHomeTask,
  homeTaskStartError,
  layoutEditing,
  reorderableHomeModules,
  proxyData,
  queueSummary,
  recentRecords,
  schedulerTaskOptions,
  schedulerModeOptions,
  schedulerTasksError,
  selectedHomeTaskId,
  selectedHomeMode,
  noticeVisible,
  noticeData,
  noticeLoading,
  greeting,
  commandTitle,
  isBootstrapping,
  statusSummary,
  wsStatus,
  backendStatus,
  toggleLayoutEditing,
  canMoveHomeModule,
  moveHomeModule,
  isHomeModuleShown,
  setHomeModuleShown,
  isHomeModuleVisible,
  onSchedulerDropdownVisibleChange,
  startHomeTask,
  retryHomeTask,
  refresh,
  showNotice,
  onNoticeConfirmed,
  formatProxyDisplay,
} = useHomeLogic()

const moduleItemKey = (key: HomeModuleKey) => key

// vuedraggable 的 #item 插槽 element 为 any，经此辅助函数收窄为 HomeModuleKey
const moduleTitle = (key: HomeModuleKey) => moduleTitleMap[key]
</script>

<style scoped>
.home-page {
  width: min(100%, 1480px);
  min-width: 0;
  margin: 0 auto;
  container: home-layout / inline-size;
}

.home-header {
  min-height: 36px;
  margin-bottom: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
}

.home-dynamic-copy {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  color: var(--v6-color-text-secondary);
  font-size: 13px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

/* 工具行六个按钮（启动脚本/添加脚本/管理插件/编辑布局/查看公告/刷新）统一默认按钮样式，
   宽度由内容自适应；仅编辑布局按钮保留 min-width，避免「完成/编辑布局」标签切换时抖动 */
.layout-edit-button {
  min-width: 104px;
}

.home-content {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 24px;
}

.home-data-error {
  margin-bottom: 16px;
}

.home-module {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  grid-column: 1 / -1;
}

/* 快速开始独立于拖拽网格，保持与网格同宽同间距 */
.home-module--command {
  margin-bottom: 24px;
}

/* DOM 顺序（homeModuleOrder）即视觉顺序，不再用 CSS order 覆盖，
   否则「编辑布局」的上移/下移与拖拽排序不会生效 */
/* 主页按 3×3 大网格心智：卫星模块 ≥2×1（12 列中占 8 列），最近活动占其余 4 列 */
.home-module--recent {
  grid-column: span 4;
}

.home-module--satellite {
  grid-column: span 8;
}

.satellite-card {
  min-height: clamp(400px, 40cqw, 560px);
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-content);
  box-shadow: var(--v6-shadow-xs);
  backdrop-filter: blur(24px) saturate(1.18);
}

.satellite-card__header {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  padding: 0 20px;
}

.satellite-card__header h2 {
  margin: 0;
  color: var(--v6-color-text);
  font-size: 15px;
  font-weight: 650;
}

.satellite-card__live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--v6-color-text-tertiary);
  font-size: 12px;
}

.satellite-card__live i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--v6-color-success);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--v6-color-success) 14%, transparent);
}

.home-module.is-hidden > :not(.module-editor-bar) {
  opacity: 0.42;
  filter: grayscale(0.18);
}

/* 编辑布局时模块编辑条兼作拖拽把手 */
.home-content .home-module.is-editing .module-editor-bar {
  cursor: grab;
}

.home-module-ghost {
  opacity: 0.38;
}

.home-module-ghost > * {
  outline: 2px dashed var(--v6-color-border-strong);
  outline-offset: 2px;
}

.home-module-chosen .module-editor-bar {
  cursor: grabbing;
  border-color: var(--v6-color-info);
}

.home-module-drag {
  opacity: 0.92;
}

@container home-layout (max-width: 800px) {
  .home-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .header-actions {
    justify-content: flex-start;
  }
}

/* 中屏：卫星占满整行，最近活动独立成行；
   卫星卡 min-height 沿用基准 clamp（40cqw 随容器收窄自动回落到 400px 下限） */
@container home-layout (max-width: 1100px) {
  .home-module--recent,
  .home-module--satellite {
    grid-column: 1 / -1;
  }
}

/* 低性能模式 / reduced-motion 下去除过渡 */
:root[data-perf-mode='low'] .home-module.is-hidden > :not(.module-editor-bar) {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .home-module.is-hidden > :not(.module-editor-bar) {
    transition: none;
  }
}
</style>
