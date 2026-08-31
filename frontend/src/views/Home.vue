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
          {{ t('home.editLayout') }}
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
          {{ t('home.viewNotice') }}
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
      :scroll-hint-hidden="scrollHintHidden"
      @reorder="reorderHomeModules"
      @visibility-change="setHomeModuleShown"
      @scroll-hint-change="setScrollHintHidden"
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

          <HomeEndfieldOverview
            v-else-if="moduleKey === 'endfield'"
            :loading="loading"
            :overview="endfieldData"
            @refresh="fetchOverviewData"
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

          <HomeSraActivityOverview
            v-else-if="moduleKey === 'starrail'"
            :title="t('home.module.starrail')"
            accent="#62c4e7"
            :empty-text="t('home.empty.starrail')"
            :loading="loading"
            :overview="starRailData"
            @refresh="fetchOverviewData"
          />

          <HomeSraActivityOverview
            v-else-if="moduleKey === 'genshin'"
            :title="t('home.module.genshin')"
            accent="#8fe3b0"
            :empty-text="t('home.empty.genshin')"
            :loading="loading"
            :overview="genshinData"
            @refresh="fetchOverviewData"
          />

          <HomeSraActivityOverview
            v-else-if="moduleKey === 'zenless'"
            :title="t('home.module.zenless')"
            accent="#ffd24a"
            :empty-text="t('home.empty.zenless')"
            :loading="loading"
            :overview="zenlessZoneZeroData"
            @refresh="fetchOverviewData"
          />

          <HomeSraActivityOverview
            v-else-if="moduleKey === 'wutheringwaves'"
            :title="t('home.module.wutheringwaves')"
            accent="#7aa2ff"
            :empty-text="t('home.empty.wutheringwaves')"
            :loading="loading"
            :overview="wutheringWavesData"
            @refresh="fetchOverviewData"
          />

          <HomeSraActivityOverview
            v-else-if="moduleKey === 'nte'"
            :title="t('home.module.nte')"
            accent="#c9a7ff"
            :empty-text="t('home.empty.nte')"
            :loading="loading"
            :overview="nevernessToEvernessData"
            @refresh="fetchOverviewData"
          />

          <HomeReverse1999Overview
            v-else-if="moduleKey === 'reverse1999'"
            :loading="loading"
            :overview="reverse1999Data"
          />
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
import { useAppInitialization } from '@/composables/useAppInitialization'
import HomeArknightsOverview from '@/views/home/components/HomeArknightsOverview.vue'
import HomeBackToTop from '@/views/home/components/HomeBackToTop.vue'
import HomeCommandCard from '@/views/home/components/HomeCommandCard.vue'
import HomeEndfieldOverview from '@/views/home/components/HomeEndfieldOverview.vue'
import HomeLayoutDrawer from '@/views/home/components/HomeLayoutDrawer.vue'
import HomeProxyCard from '@/views/home/components/HomeProxyCard.vue'
import HomeQuickActionsCard from '@/views/home/components/HomeQuickActionsCard.vue'
import HomeReverse1999Overview from '@/views/home/components/HomeReverse1999Overview.vue'
import HomeSraActivityOverview from '@/views/home/components/HomeSraActivityOverview.vue'
import HomeScrollHint from '@/views/home/components/HomeScrollHint.vue'
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
  scrollHintHidden,
  loadHomeLayout,
  reorderHomeModules,
  setHomeModuleShown,
  setScrollHintHidden,
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
  endfieldData,
  starRailData,
  genshinData,
  zenlessZoneZeroData,
  wutheringWavesData,
  nevernessToEvernessData,
  reverse1999Data,
  clearOverviewError,
  fetchOverviewData,
} = useHomeOverview()

const { t } = useI18n()

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 11) {
    return t('home.greeting.morning')
  } else if (hour >= 11 && hour < 14) {
    return t('home.greeting.noon')
  } else if (hour >= 14 && hour < 18) {
    return t('home.greeting.afternoon')
  } else if (hour >= 18 && hour < 23) {
    return t('home.greeting.evening')
  } else {
    return t('home.greeting.night')
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
