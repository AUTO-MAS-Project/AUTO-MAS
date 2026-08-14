<template>
  <div class="home-page">
    <div class="home-header">
      <div>
        <a-typography-title :level="2" class="home-title">{{ greeting }}</a-typography-title>
      </div>

      <div class="header-actions">
        <a-button
          :type="layoutDrawerOpen ? 'primary' : 'default'"
          class="layout-edit-button"
          @click="layoutDrawerOpen = !layoutDrawerOpen"
        >
          <template #icon>
            <EditOutlined />
          </template>
          编辑布局
        </a-button>
        <a-button
          type="primary"
          ghost
          :loading="noticeLoading"
          class="notice-button"
          @click="showNotice"
        >
          <template #icon>
            <BellOutlined />
          </template>
          查看公告
        </a-button>
      </div>
    </div>

    <NoticeModal
      v-model:visible="noticeVisible"
      :notice-data="noticeData"
      @confirmed="onNoticeConfirmed"
    />

    <HomeLayoutDrawer
      v-model:open="layoutDrawerOpen"
      :modules="homeModules"
      @reorder="reorderHomeModules"
      @visibility-change="setHomeModuleShown"
    />

    <div v-if="layoutReady && !isBootstrapping" class="home-content">
      <template v-for="moduleKey in homeModuleOrder" :key="moduleKey">
        <section v-if="isHomeModuleVisible(moduleKey)" class="home-module">
          <HomeCommandCard
            v-if="moduleKey === 'command'"
            v-model:selected-task-id="selectedHomeTaskId"
            :is-bootstrapping="isBootstrapping"
            :command-title="commandTitle"
            :command-author="commandAuthor"
            :scheduler-task-options="schedulerTaskOptions"
            :scheduler-tasks-loading="schedulerTasksLoading"
            :starting-home-task="startingHomeTask"
            @dropdown-visible-change="onSchedulerDropdownVisibleChange"
            @start="startHomeTask"
          />

          <HomeQuickActionsCard v-else-if="moduleKey === 'quick'" />

          <section v-else-if="moduleKey === 'satellite'" class="satellite-animation-section">
            <SatelliteAnimation v-show="!performanceStore.isBackgrounded" />
          </section>

          <HomeProxyCard
            v-else-if="moduleKey === 'proxy'"
            :loading="loading"
            :proxy-data="proxyData"
          />

          <HomeArknightsOverview
            v-else-if="moduleKey === 'arknights'"
            :loading="loading"
            :error="error"
            :activity-data="activityData"
            :resource-data="resourceData"
            @refresh="fetchOverviewData"
            @clear-error="clearOverviewError"
          />
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { BellOutlined, EditOutlined } from '@ant-design/icons-vue'
import NoticeModal from '@/components/NoticeModal.vue'
import SatelliteAnimation from '@/components/SatelliteAnimation.vue'
import { useAppInitialization } from '@/composables/useAppInitialization'
import HomeArknightsOverview from '@/views/home/components/HomeArknightsOverview.vue'
import HomeCommandCard from '@/views/home/components/HomeCommandCard.vue'
import HomeLayoutDrawer from '@/views/home/components/HomeLayoutDrawer.vue'
import HomeProxyCard from '@/views/home/components/HomeProxyCard.vue'
import HomeQuickActionsCard from '@/views/home/components/HomeQuickActionsCard.vue'
import { useHomeLayout } from '@/views/home/useHomeLayout'
import { useHomeNotice } from '@/views/home/useHomeNotice'
import { useHomeOverview } from '@/views/home/useHomeOverview'
import { useHomeQuickStart } from '@/views/home/useHomeQuickStart'
import { usePerformanceStore } from '@/stores/performance'

defineOptions({
  name: 'HomeView',
})

const { isBootstrapping } = useAppInitialization()
const performanceStore = usePerformanceStore()
const {
  layoutReady,
  layoutDrawerOpen,
  homeModuleOrder,
  homeModules,
  loadHomeLayout,
  reorderHomeModules,
  setHomeModuleShown,
  isHomeModuleVisible,
} = useHomeLayout()
const { noticeVisible, noticeData, noticeLoading, fetchNoticeData, onNoticeConfirmed, showNotice } =
  useHomeNotice()
const {
  commandTitle,
  commandAuthor,
  schedulerTasksLoading,
  startingHomeTask,
  schedulerTaskOptions,
  selectedHomeTaskId,
  fetchSchedulerTaskOptions,
  onSchedulerDropdownVisibleChange,
  startHomeTask,
} = useHomeQuickStart()
const {
  loading,
  error,
  activityData,
  resourceData,
  proxyData,
  clearOverviewError,
  fetchOverviewData,
} = useHomeOverview()

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 11) {
    return '早上好！欢迎使用 AUTO-MAS'
  } else if (hour >= 11 && hour < 14) {
    return '中午好！欢迎使用 AUTO-MAS'
  } else if (hour >= 14 && hour < 18) {
    return '下午好！欢迎使用 AUTO-MAS'
  } else if (hour >= 18 && hour < 23) {
    return '晚上好！欢迎使用 AUTO-MAS'
  } else {
    return '夜深了，欢迎使用 AUTO-MAS'
  }
})

const loadHomeData = () => {
  fetchSchedulerTaskOptions({ quiet: true })
  fetchOverviewData()
  fetchNoticeData()
}

onMounted(async () => {
  await loadHomeLayout()

  if (isBootstrapping.value) {
    loading.value = true
    noticeLoading.value = true

    const stopWatching = watch(isBootstrapping, bootstrapping => {
      if (bootstrapping) {
        return
      }

      stopWatching()
      loadHomeData()
    })
    return
  }

  loadHomeData()
})
</script>

<style scoped>
.home-page {
  max-width: 1480px;
  margin: 0 auto;
}

.home-header {
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.home-title {
  margin: 0 0 4px;
  color: var(--ant-color-text);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.layout-edit-button {
  min-width: 104px;
}

.notice-button {
  min-width: 120px;
}

.home-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.satellite-animation-section {
  width: 100%;
  margin-top: 0;
}

.home-module {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

@media (max-width: 800px) {
  .home-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .header-actions {
    justify-content: flex-start;
  }
}
</style>
