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
      :activity-modules="homeActivityModules"
      :scroll-hint-hidden="scrollHintHidden"
      :carousel-autoplay="carouselAutoplay"
      @reorder="reorderHomeModules"
      @reorder-activities="reorderActivityModules"
      @visibility-change="setHomeModuleShown"
      @scroll-hint-change="setScrollHintHidden"
      @autoplay-change="setCarouselAutoplay"
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

          <!-- 各游戏活动卡收进一个 banner 轮播：顶部横幅兼作切换器，下方只渲染当前游戏 -->
          <HomeActivityCarousel
            v-else-if="moduleKey === 'activities'"
            :items="activityBanners"
            :autoplay="carouselAutoplay"
          >
            <template #detail="{ moduleKey: gameKey }">
              <HomeEndfieldOverview
                v-if="gameKey === 'endfield'"
                :loading="endfieldSource.loading.value"
                :overview="endfieldSource.overview.value"
                @refresh="endfieldSource.refresh"
              />

              <HomeArknightsOverview
                v-else-if="gameKey === 'arknights'"
                :loading="loading"
                :error="error"
                :activity-data="activityData"
                :resource-data="resourceData"
                @refresh="fetchOverviewData"
                @clear-error="clearOverviewError"
              />

              <HomeSraActivityOverview
                v-else-if="gameKey === 'starrail'"
                :title="t('home.module.starrail')"
                :accent="getActivityAccent('starrail')"
                :empty-text="t('home.empty.starrail')"
                :loading="starRailSource.loading.value"
                :overview="starRailSource.overview.value"
                @refresh="starRailSource.refresh"
              />

              <HomeSraActivityOverview
                v-else-if="gameKey === 'genshin'"
                :title="t('home.module.genshin')"
                :accent="getActivityAccent('genshin')"
                :empty-text="t('home.empty.genshin')"
                :loading="genshinSource.loading.value"
                :overview="genshinSource.overview.value"
                @refresh="genshinSource.refresh"
              />

              <HomeSraActivityOverview
                v-else-if="gameKey === 'zenless'"
                :title="t('home.module.zenless')"
                :accent="getActivityAccent('zenless')"
                :empty-text="t('home.empty.zenless')"
                :loading="zenlessSource.loading.value"
                :overview="zenlessSource.overview.value"
                @refresh="zenlessSource.refresh"
              />

              <HomeSraActivityOverview
                v-else-if="gameKey === 'wutheringwaves'"
                :title="t('home.module.wutheringwaves')"
                :accent="getActivityAccent('wutheringwaves')"
                :empty-text="t('home.empty.wutheringwaves')"
                :loading="wutheringWavesSource.loading.value"
                :overview="wutheringWavesSource.overview.value"
                @refresh="wutheringWavesSource.refresh"
              />

              <HomeSraActivityOverview
                v-else-if="gameKey === 'nte'"
                :title="t('home.module.nte')"
                :accent="getActivityAccent('nte')"
                :empty-text="t('home.empty.nte')"
                :loading="nevernessToEvernessSource.loading.value"
                :overview="nevernessToEvernessSource.overview.value"
                @refresh="nevernessToEvernessSource.refresh"
              />

              <HomeReverse1999Overview
                v-else-if="gameKey === 'reverse1999'"
                :loading="reverse1999Source.loading.value"
                :overview="reverse1999Source.overview.value"
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
import { useAppInitialization } from '@/composables/useAppInitialization'
import HomeActivityCarousel from '@/views/home/components/HomeActivityCarousel.vue'
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
import {
  arknightsActivityBanner,
  endfieldActivityBanner,
  getActivityAccent,
  sraActivityBanner,
} from '@/views/home/activityBanner'
import { useHomeLayout } from '@/views/home/useHomeLayout'
import { useHomeNotice } from '@/views/home/useHomeNotice'
import { useHomeOverview } from '@/views/home/useHomeOverview'
import { useSraActivitySource } from '@/views/home/useSraActivitySource'
import { useReverse1999ActivitySource } from '@/views/home/useReverse1999ActivitySource'
import { useEndfieldActivitySource } from '@/views/home/useEndfieldActivitySource'
import { useHomeQuickStart } from '@/views/home/useHomeQuickStart'
import { usePerformanceStore } from '@/stores/performance'
import { createEmptySraActivityOverview } from '@/types/home'
import type { ActivityBannerItem, HomeModuleKey } from '@/types/home'

defineOptions({
  name: 'HomeView',
})

const { isBootstrapping } = useAppInitialization()
const performanceStore = usePerformanceStore()
const {
  layoutReady,
  layoutDrawerOpen,
  homeTopLevelOrder,
  homeModules,
  homeActivityModules,
  visibleActivityKeys,
  scrollHintHidden,
  carouselAutoplay,
  loadHomeLayout,
  reorderHomeModules,
  reorderActivityModules,
  setHomeModuleShown,
  setScrollHintHidden,
  setCarouselAutoplay,
  isHomeModuleVisible,
} = useHomeLayout()
const { noticeVisible, noticeData, noticeLoading, fetchNoticeData, onNoticeConfirmed, showNotice } =
  useHomeNotice()
const {
  commandTitle,
  commandAuthor,
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
  activityData,
  resourceData,
  proxyData,
  clearOverviewError,
  fetchOverviewData,
} = useHomeOverview()

const { t } = useI18n()

// 首页全前端化：SRA 五张活动卡直连公开接口，独立快照/失败态，不再依赖聚合接口
const starRailSource = useSraActivitySource('sr', t('home.module.starrail'))
const genshinSource = useSraActivitySource('ys', t('home.module.genshin'))
const zenlessSource = useSraActivitySource('zzz', t('home.module.zenless'))
const wutheringWavesSource = useSraActivitySource('ww', t('home.module.wutheringwaves'))
const nevernessToEvernessSource = useSraActivitySource('nte', t('home.module.nte'))
const reverse1999Source = useReverse1999ActivitySource()
const endfieldSource = useEndfieldActivitySource()

const sraSourceFor = (key: HomeModuleKey) => {
  switch (key) {
    case 'starrail':
      return starRailSource
    case 'genshin':
      return genshinSource
    case 'zenless':
      return zenlessSource
    case 'wutheringwaves':
      return wutheringWavesSource
    case 'nte':
      return nevernessToEvernessSource
    case 'reverse1999':
      return reverse1999Source
    default:
      return null
  }
}

// 轮播只展示没被单独关掉的游戏；顺序跟着「编辑布局」里的排序走
const activityBanners = computed<ActivityBannerItem[]>(() =>
  visibleActivityKeys.value.map(key => {
    const base = {
      key,
      title: t(`home.game.${key}`),
      accent: getActivityAccent(key),
    }

    if (key === 'endfield') {
      return {
        ...base,
        loading: endfieldSource.loading.value,
        ...endfieldActivityBanner(endfieldSource.overview.value),
      }
    }

    if (key === 'arknights') {
      return {
        ...base,
        loading: loading.value,
        ...arknightsActivityBanner(activityData.value),
      }
    }

    const source = sraSourceFor(key)
    return {
      ...base,
      loading: source?.loading.value ?? false,
      ...sraActivityBanner(source?.overview.value ?? createEmptySraActivityOverview()),
    }
  })
)

// 只有模块可见时才拉活动数据；布局要等 loadHomeLayout 读回来才知道哪些模块被隐藏，
// 所以以 layoutReady 为闸；隐藏时停掉重试定时器，卸载时由各源的 onScopeDispose 收尾
const activitySourcesByModule: Array<[HomeModuleKey, { start: () => void; stop: () => void }]> = [
  ['starrail', starRailSource],
  ['genshin', genshinSource],
  ['zenless', zenlessSource],
  ['wutheringwaves', wutheringWavesSource],
  ['nte', nevernessToEvernessSource],
  ['reverse1999', reverse1999Source],
  ['endfield', endfieldSource],
]
for (const [moduleKey, source] of activitySourcesByModule) {
  watch(
    // 各游戏活动源现在都收在「活动轮播」模块里：整个轮播被隐藏时同样不拉数据
    () =>
      layoutReady.value &&
      isHomeModuleVisible('activities') &&
      isHomeModuleVisible(moduleKey),
    visible => (visible ? source.start() : source.stop()),
    { immediate: true }
  )
}

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

const loadHomeData = async () => {
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
