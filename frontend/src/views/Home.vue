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
          {{ t('core.home.editLayout') }}
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
          {{ t('core.home.viewNotice') }}
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
      :activity-modules="homeActivityModules"
      :scroll-hint-hidden="scrollHintHidden"
      :carousel-autoplay="carouselAutoplay"
      :activity-notes-visible="activityNotesVisible"
      :hidden-activity-notes="hiddenActivityNotes"
      @reorder="reorderHomeModules"
      @reorder-activities="reorderActivityModules"
      @visibility-change="setHomeModuleShown"
      @scroll-hint-change="setScrollHintHidden"
      @autoplay-change="setCarouselAutoplay"
      @activity-note-visibility-change="setActivityNoteShown"
    />

    <div v-if="layoutReady" class="home-content">
      <template v-for="moduleKey in homeTopLevelOrder" :key="moduleKey">
        <section v-if="isHomeModuleVisible(moduleKey)" class="home-module">
          <HomeCommandCard
            v-if="moduleKey === 'command'"
            :selected-task-ids="selectedHomeTaskIds"
            :is-bootstrapping="isBootstrapping"
            :command-title="commandTitle"
            :command-author="commandAuthor"
            :scheduler-task-options="schedulerTaskOptions"
            :scheduler-tasks-loading="schedulerTasksLoading"
            :scheduler-tasks-unavailable="schedulerTasksUnavailable"
            :starting-home-task="startingHomeTask"
            @update:selected-task-ids="updateSelectedHomeTaskIds"
            @dropdown-visible-change="onSchedulerDropdownVisibleChange"
            @start="startHomeTask"
            @refresh-greeting="refreshGreeting"
          />

          <HomeQuickActionsCard v-else-if="moduleKey === 'quick'" />

          <section v-else-if="moduleKey === 'satellite'" class="satellite-animation-section">
            <template v-if="homeSatelliteStore.initialized">
              <SatelliteClassic
                v-if="homeSatelliteStore.style === 'classic'"
                v-show="!performanceStore.isBackgrounded"
              />
              <SatelliteAnimation v-else v-show="!performanceStore.isBackgrounded" />
            </template>
          </section>

          <HomeProxyCard
            v-else-if="moduleKey === 'proxy'"
            :loading="loading"
            :proxy-data="proxyData"
          />

          <!-- 各游戏共用主视觉与活动侧栏，卡池、资源关卡等补充内容按需放在下方。 -->
          <HomeActivityCarousel
            v-else-if="moduleKey === 'activities'"
            :items="activities.panels.value"
            :autoplay="carouselAutoplay"
            @refresh="activities.refresh"
            @select="activities.select"
            @action="activities.action"
            @dismiss="clearOverviewError"
          >
            <template #community="{ moduleKey: gameKey }">
              <!-- 社区信息紧跟游戏切换条，两者都不吸顶，跟着页面一起滚 -->
              <HomeActivityNotes
                v-if="activityNotesVisible && isActivityNoteVisible(gameKey)"
                :active-key="gameKey"
              />
            </template>
          </HomeActivityCarousel>
        </section>
      </template>
    </div>

    <HomeScrollHint v-if="!scrollHintHidden" />
    <HomeBackToTop />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, watch } from 'vue'
import { BellOutlined, EditOutlined } from '@ant-design/icons-vue'
import NoticeModal from '@/components/NoticeModal.vue'
import SatelliteAnimation from '@/components/SatelliteAnimation.vue'
import SatelliteClassic from '@/components/SatelliteClassic.vue'
import { useAppInitialization } from '@/composables/useAppInitialization'
import HomeActivityCarousel from '@/views/home/components/HomeActivityCarousel.vue'
import HomeBackToTop from '@/views/home/components/HomeBackToTop.vue'
import HomeActivityNotes from '@/views/home/components/HomeActivityNotes.vue'
import HomeCommandCard from '@/views/home/components/HomeCommandCard.vue'
import HomeLayoutDrawer from '@/views/home/components/HomeLayoutDrawer.vue'
import HomeProxyCard from '@/views/home/components/HomeProxyCard.vue'
import HomeQuickActionsCard from '@/views/home/components/HomeQuickActionsCard.vue'
import HomeScrollHint from '@/views/home/components/HomeScrollHint.vue'
import { useHomeActivities } from '@/views/home/useHomeActivities'
import { useHomeLayout } from '@/views/home/useHomeLayout'
import { useHomeNotice } from '@/views/home/useHomeNotice'
import { useHomeOverview } from '@/views/home/useHomeOverview'
import { useHomeQuickStart } from '@/views/home/useHomeQuickStart'
import { usePerformanceStore } from '@/stores/performance'
import { useHomeSatelliteStore } from '@/stores/homeSatellite'

defineOptions({
  name: 'HomeView',
})

const { isBootstrapping } = useAppInitialization()
const performanceStore = usePerformanceStore()
// 卫星样式读到之前先不出卫星，免得先按默认建一遍再换成用户选的那种
const homeSatelliteStore = useHomeSatelliteStore()
void homeSatelliteStore.load()
const {
  layoutReady,
  layoutDrawerOpen,
  homeTopLevelOrder,
  homeModules,
  homeActivityModules,
  visibleActivityKeys,
  scrollHintHidden,
  carouselAutoplay,
  activityNotesVisible,
  hiddenActivityNotes,
  loadHomeLayout,
  loadManagedActivityModules,
  reorderHomeModules,
  reorderActivityModules,
  setHomeModuleShown,
  setScrollHintHidden,
  setCarouselAutoplay,
  setActivityNoteShown,
  isActivityNoteVisible,
  isHomeModuleVisible,
} = useHomeLayout()
const { noticeVisible, noticeData, noticeLoading, fetchNoticeData, onNoticeConfirmed, showNotice } =
  useHomeNotice()
const {
  commandTitle,
  commandAuthor,
  refreshGreeting,
  schedulerTasksLoading,
  schedulerTasksUnavailable,
  startingHomeTask,
  schedulerTaskOptions,
  selectedHomeTaskIds,
  restoreSelectedHomeTaskIds,
  updateSelectedHomeTaskIds,
  fetchSchedulerTaskOptions,
  onSchedulerDropdownVisibleChange,
  startHomeTask,
} = useHomeQuickStart()
const {
  loading,
  error,
  hasSnapshot,
  /** 今日开放的资源收集关卡，给明日方舟卡片用 */
  resourceData,
  proxyData,
  clearOverviewError,
  fetchOverviewData,
} = useHomeOverview()

const { t } = useI18n()

const activities = useHomeActivities({
  visibleKeys: visibleActivityKeys,
  resources: resourceData,
  resourceError: error,
})

// 布局加载后只启动可见模块；隐藏或卸载时由各数据源停止重试与请求。
for (const [moduleKey, source] of activities.sources) {
  watch(
    () => layoutReady.value && isHomeModuleVisible('activities') && isHomeModuleVisible(moduleKey),
    visible => (visible ? source.start() : source.stop()),
    { immediate: true }
  )
}

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 11) {
    return t('core.home.greeting.morning')
  } else if (hour >= 11 && hour < 14) {
    return t('core.home.greeting.noon')
  } else if (hour >= 14 && hour < 18) {
    return t('core.home.greeting.afternoon')
  } else if (hour >= 18 && hour < 23) {
    return t('core.home.greeting.evening')
  } else {
    return t('core.home.greeting.night')
  }
})

const loadHomeData = async () => {
  void loadManagedActivityModules()
  await restoreSelectedHomeTaskIds()
  fetchSchedulerTaskOptions({ quiet: true })
  fetchOverviewData()
  fetchNoticeData()
}

onMounted(async () => {
  await loadHomeLayout()

  if (isBootstrapping.value) {
    // 已有快照时直接展示内容，刷新不再用骨架遮挡；无快照时显示加载态
    if (!hasSnapshot.value) {
      loading.value = true
    }
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
  max-width: 1600px;
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
