<template>
  <div class="home-page">
    <div class="home-header">
      <div>
        <a-typography-title :level="2" class="home-title">{{ greeting }}</a-typography-title>
      </div>

      <div class="header-actions">
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

    <div class="home-content">
      <template v-for="moduleKey in homeModuleOrder" :key="moduleKey">
        <section
          v-if="isHomeModuleVisible(moduleKey)"
          class="home-module"
          :class="{ 'is-editing': layoutEditing }"
        >
          <div v-if="layoutEditing" class="module-editor-bar">
            <div class="module-editor-title">{{ moduleTitleMap[moduleKey] }}</div>
            <div v-if="moduleKey === 'arknights'" class="module-editor-extra">
              <span>默认展开</span>
              <a-switch
                size="small"
                :checked="arknightsDefaultExpanded"
                @change="setArknightsDefaultExpanded"
              />
            </div>
            <div class="module-editor-actions">
              <a-tooltip title="上移">
                <a-button
                  type="text"
                  size="small"
                  :disabled="!canMoveHomeModule(moduleKey, 'up')"
                  @click="moveHomeModule(moduleKey, 'up')"
                >
                  <template #icon>
                    <ArrowUpOutlined />
                  </template>
                </a-button>
              </a-tooltip>
              <a-tooltip title="下移">
                <a-button
                  type="text"
                  size="small"
                  :disabled="!canMoveHomeModule(moduleKey, 'down')"
                  @click="moveHomeModule(moduleKey, 'down')"
                >
                  <template #icon>
                    <ArrowDownOutlined />
                  </template>
                </a-button>
              </a-tooltip>
            </div>
          </div>

          <a-card v-if="moduleKey === 'command'" class="command-card">
            <section class="command-panel" aria-label="调度快速启动">
              <div class="command-main">
                <div class="command-title">准备好下一轮自动化</div>
              </div>

              <div class="scheduler-launcher">
                <div class="launcher-header">
                  <div>
                    <div class="launcher-title">快速开始</div>
                  </div>
                </div>

                <div class="launcher-controls">
                  <a-select
                    v-model:value="selectedHomeTaskId"
                    class="launcher-select"
                    :options="schedulerTaskOptions"
                    :loading="schedulerTasksLoading"
                    size="large"
                    placeholder="选择任务"
                    @dropdown-visible-change="onSchedulerDropdownVisibleChange"
                  />
                  <a-button
                    type="primary"
                    size="large"
                    class="launcher-start"
                    :loading="startingHomeTask"
                    :disabled="!selectedHomeTaskId"
                    @click="startHomeTask"
                  >
                    <template #icon>
                      <PlayCircleOutlined />
                    </template>
                    开始
                  </a-button>
                </div>
              </div>
            </section>
          </a-card>

          <a-card v-else-if="moduleKey === 'quick'" class="shortcut-card" title="常用入口">
            <section class="quick-actions" aria-label="快捷入口">
              <button
                v-for="action in quickActions"
                :key="action.path"
                type="button"
                class="quick-action"
                @click="navigateTo(action.path)"
              >
                <span class="quick-action-icon">
                  <component :is="action.icon" />
                </span>
                <span class="quick-action-text">
                  <span class="quick-action-title">{{ action.title }}</span>
                  <span class="quick-action-desc">{{ action.description }}</span>
                </span>
              </button>
            </section>
          </a-card>

          <section v-else-if="moduleKey === 'satellite'" class="satellite-animation-section">
            <SatelliteAnimation />
          </section>

          <section v-else-if="moduleKey === 'proxy'" class="overview-grid" aria-label="代理状态">
            <a-card class="proxy-card" title="代理状态" :loading="loading">
              <div v-if="Object.keys(proxyData).length > 0" class="proxy-list">
                <a-row :gutter="[16, 16]">
                  <a-col
                    v-for="(proxy, username) in proxyData"
                    :key="username"
                    :xs="24"
                    :lg="12"
                    :xl="8"
                  >
                    <div class="proxy-item">
                      <div class="proxy-header">
                        <div class="proxy-username">
                          <UserOutlined class="user-icon" />
                          <span class="username">{{ username }}</span>
                        </div>
                      </div>

                      <div class="proxy-stats">
                        <div class="stat-item full-width">
                          <a-statistic
                            title="最后代理时间"
                            :value="formatProxyDisplay(proxy.LastProxyDate)"
                          />
                        </div>
                        <div class="stat-pair">
                          <a-statistic title="代理次数" :value="proxy.ProxyTimes" />
                          <a-statistic
                            title="错误次数"
                            :value="proxy.ErrorTimes"
                            :value-style="{ color: proxy.ErrorTimes > 0 ? '#ff4d4f' : undefined }"
                          />
                        </div>
                      </div>
                    </div>
                  </a-col>
                </a-row>
              </div>

              <div v-else-if="!loading" class="empty-state">
                <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
              </div>
            </a-card>
          </section>

          <a-collapse
            v-else-if="moduleKey === 'arknights'"
            v-model:active-key="activeCollapseKeys"
            class="arknights-collapse"
          >
            <a-collapse-panel key="arknights" header="明日方舟活动信息">
              <div v-if="error" class="error-message">
                <a-alert :message="error" type="error" show-icon closable @close="error = ''" />
              </div>

              <a-card
                v-if="activityData?.length"
                title="当期活动关卡"
                class="activity-card"
                :loading="loading"
              >
                <div v-if="currentActivity && !loading" class="activity-info">
                  <div class="activity-header">
                    <div class="activity-left">
                      <div class="activity-name">
                        <span class="activity-title">{{ currentActivity.Tip }}</span>
                      </div>
                      <div class="activity-end-time">
                        <ClockCircleOutlined class="time-icon" />
                        <span class="time-label">结束时间：</span>
                        <span class="time-value">{{
                          formatTime(currentActivity.UtcExpireTime)
                        }}</span>
                      </div>
                    </div>

                    <div class="activity-right">
                      <a-statistic-countdown
                        v-if="getActivityTimeStatus(currentActivity.UtcExpireTime) === 'ended'"
                        title=""
                        :value="getCountdownValue(currentActivity.UtcExpireTime)"
                        format="活动已结束"
                        :value-style="{
                          color: '#ff4d4f',
                          fontWeight: 'bold',
                          fontSize: '18px',
                        }"
                        @finish="onCountdownFinish"
                      />

                      <a-statistic-countdown
                        v-else-if="
                          getActivityTimeStatus(currentActivity.UtcExpireTime) === 'warning'
                        "
                        title="当期活动剩余时间"
                        :value="getCountdownValue(currentActivity.UtcExpireTime)"
                        format="D 天 H 时 m 分 ss 秒 SSS 毫秒"
                        class="rainbow-text"
                        @finish="onCountdownFinish"
                      />

                      <a-statistic-countdown
                        v-else
                        title="当期活动剩余时间"
                        :value="getCountdownValue(currentActivity.UtcExpireTime)"
                        format="D 天 H 时 m 分"
                        :value-style="{
                          color: 'var(--ant-color-text)',
                          fontWeight: '600',
                          fontSize: '20px',
                        }"
                        @finish="onCountdownFinish"
                      />
                    </div>
                  </div>
                </div>

                <div class="activity-list">
                  <div v-for="item in activityData" :key="item.Value" class="activity-item">
                    <div class="stage-info">
                      <div class="stage-name">{{ item.Display }}</div>
                    </div>

                    <div class="drop-info">
                      <div class="drop-image">
                        <img
                          v-if="getMaterialImage(item.Drop)"
                          :src="getMaterialImage(item.Drop)"
                          :alt="item.DropName"
                          @error="handleImageError"
                        />
                      </div>

                      <div class="drop-details">
                        <div class="drop-name">{{ item.DropName }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </a-card>

              <a-card title="今日开放资源收集关卡" class="resource-card" :loading="loading">
                <div v-if="resourceData?.length" class="resource-list">
                  <div v-for="item in resourceData" :key="item.Value" class="resource-item">
                    <div class="stage-info">
                      <div class="stage-name">{{ item.Display }}</div>
                    </div>

                    <div class="drop-info">
                      <div class="drop-image">
                        <img
                          v-if="getMaterialImage(item.Drop)"
                          :src="getMaterialImage(item.Drop)"
                          :alt="item.DropName"
                          @error="handleImageError"
                        />
                      </div>

                      <div class="drop-details">
                        <div class="drop-name">{{ item.DropName }}</div>
                        <div class="drop-tip">{{ item.Activity.Tip }}</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else-if="!loading" class="empty-state">
                  <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
                </div>
              </a-card>
            </a-collapse-panel>
          </a-collapse>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  BellOutlined,
  CalendarOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  ControlOutlined,
  DatabaseOutlined,
  EditOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import NoticeModal from '@/components/NoticeModal.vue'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useAppInitialization } from '@/composables/useAppInitialization'
import SatelliteAnimation from '@/components/SatelliteAnimation.vue'
import { OpenAPI } from '@/api'
import type { ComboBoxItem } from '@/api'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import { navigateTo } from '@/router'

defineOptions({
  name: 'HomeView',
})

const logger = window.electronAPI.getLogger('首页')

interface ActivityInfo {
  Tip: string
  StageName: string
  UtcStartTime: string
  UtcExpireTime: string
  TimeZone: number
}

interface ActivityItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: ActivityInfo
}

interface ProxyInfo {
  LastProxyDate: string
  ProxyTimes: number
  ErrorTimes: number
  ErrorInfo: Record<string, any>
}

interface ApiResponse {
  Stage: {
    Activity: ActivityItem[]
    Resource: ResourceItem[]
  }
  Proxy: Record<string, ProxyInfo>
}

interface ResourceItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: {
    Tip: string
    StageName: string
  }
}

type HomeModuleKey = 'command' | 'quick' | 'satellite' | 'proxy' | 'arknights'
type HomeModuleDirection = 'up' | 'down'

interface HomeLayoutConfig {
  moduleOrder: HomeModuleKey[]
  arknightsDefaultExpanded: boolean
}

const HOME_LAYOUT_STORAGE_KEY = 'auto-mas.home.layout'
const defaultHomeModuleOrder: HomeModuleKey[] = [
  'command',
  'quick',
  'satellite',
  'proxy',
  'arknights',
]
const moduleTitleMap: Record<HomeModuleKey, string> = {
  command: '快速开始',
  quick: '常用入口',
  satellite: '卫星环绕',
  proxy: '代理状态',
  arknights: '明日方舟活动信息',
}

const quickActions = [
  {
    title: '脚本管理',
    description: '配置自动化脚本',
    path: '/scripts',
    icon: FileTextOutlined,
  },
  {
    title: '计划管理',
    description: '编排运行计划',
    path: '/plans',
    icon: CalendarOutlined,
  },
  {
    title: '模拟器管理',
    description: '维护设备环境',
    path: '/emulators',
    icon: DatabaseOutlined,
  },
  {
    title: '调度队列',
    description: '查看排队任务',
    path: '/queue',
    icon: UnorderedListOutlined,
  },
  {
    title: '调度中心',
    description: '控制执行状态',
    path: '/scheduler',
    icon: ControlOutlined,
  },
]

const mockSchedulerTasks: ComboBoxItem[] = [
  { label: '队列 - 每日自动化', value: 'mock-daily-queue' },
  { label: '脚本 - 通用巡检', value: 'mock-general-check' },
  { label: '队列 - 夜间批处理', value: 'mock-nightly-queue' },
]

const loading = ref(false)
const schedulerTasksLoading = ref(false)
const startingHomeTask = ref(false)
const error = ref('')
const activeCollapseKeys = ref<string[]>([])
const layoutEditing = ref(false)
const arknightsDefaultExpanded = ref(false)
const homeModuleOrder = ref<HomeModuleKey[]>([...defaultHomeModuleOrder])
const activityData = ref<ActivityItem[]>([])
const resourceData = ref<ResourceItem[]>([])
const proxyData = ref<Record<string, ProxyInfo>>({})
const schedulerTaskOptions = ref<ComboBoxItem[]>(mockSchedulerTasks)
const selectedHomeTaskId = ref<string | null>(mockSchedulerTasks[0]?.value ?? null)
const selectedHomeMode = ref<TaskCreateIn.mode>(TaskCreateIn.mode.AUTO_PROXY)

const noticeVisible = ref(false)
const noticeData = ref<Record<string, string>>({})
const noticeLoading = ref(false)
const { isBootstrapping } = useAppInitialization()
const { playSound } = useAudioPlayer()

const currentActivity = computed(() => {
  if (!activityData.value.length) return null
  return activityData.value[0]?.Activity
})

const hasArknightsData = computed(() => {
  return activityData.value.length > 0 || resourceData.value.length > 0
})

const isHomeModuleKey = (value: unknown): value is HomeModuleKey => {
  return typeof value === 'string' && defaultHomeModuleOrder.includes(value as HomeModuleKey)
}

const normalizeHomeModuleOrder = (order: unknown): HomeModuleKey[] => {
  const configuredOrder = Array.isArray(order) ? order.filter(isHomeModuleKey) : []
  const uniqueOrder = configuredOrder.filter((key, index, array) => array.indexOf(key) === index)
  const missingOrder = defaultHomeModuleOrder.filter(key => !uniqueOrder.includes(key))
  return [...uniqueOrder, ...missingOrder]
}

const persistHomeLayoutConfig = () => {
  try {
    const config: HomeLayoutConfig = {
      moduleOrder: homeModuleOrder.value,
      arknightsDefaultExpanded: arknightsDefaultExpanded.value,
    }
    localStorage.setItem(HOME_LAYOUT_STORAGE_KEY, JSON.stringify(config))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`保存首页布局配置失败: ${errorMsg}`)
  }
}

const applyArknightsDefaultExpanded = () => {
  activeCollapseKeys.value = arknightsDefaultExpanded.value ? ['arknights'] : []
}

const loadHomeLayoutConfig = () => {
  try {
    const rawConfig = localStorage.getItem(HOME_LAYOUT_STORAGE_KEY)
    if (rawConfig) {
      const config = JSON.parse(rawConfig) as Partial<HomeLayoutConfig>
      homeModuleOrder.value = normalizeHomeModuleOrder(config.moduleOrder)
      arknightsDefaultExpanded.value = Boolean(config.arknightsDefaultExpanded)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取首页布局配置失败: ${errorMsg}`)
  }

  applyArknightsDefaultExpanded()
}

const toggleLayoutEditing = () => {
  layoutEditing.value = !layoutEditing.value
}

const canMoveHomeModule = (key: HomeModuleKey, direction: HomeModuleDirection) => {
  const currentIndex = homeModuleOrder.value.indexOf(key)
  if (currentIndex < 0) {
    return false
  }

  return direction === 'up' ? currentIndex > 0 : currentIndex < homeModuleOrder.value.length - 1
}

const moveHomeModule = (key: HomeModuleKey, direction: HomeModuleDirection) => {
  if (!canMoveHomeModule(key, direction)) {
    return
  }

  const currentIndex = homeModuleOrder.value.indexOf(key)
  const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1
  const nextOrder = [...homeModuleOrder.value]
  const currentModule = nextOrder[currentIndex]
  const targetModule = nextOrder[targetIndex]
  if (!currentModule || !targetModule) {
    return
  }

  nextOrder[currentIndex] = targetModule
  nextOrder[targetIndex] = currentModule
  homeModuleOrder.value = nextOrder
  persistHomeLayoutConfig()
}

const setArknightsDefaultExpanded = (checked: boolean | string | number) => {
  arknightsDefaultExpanded.value = Boolean(checked)
  applyArknightsDefaultExpanded()
  persistHomeLayoutConfig()
}

const isHomeModuleVisible = (key: HomeModuleKey) => {
  return key !== 'arknights' || layoutEditing.value || hasArknightsData.value
}

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

const formatProxyDisplay = (dateStr: string) => {
  if (dateStr === '暂无代理数据') {
    return dateStr
  }
  return formatBackendDateTime(dateStr)
}

const formatTime = (timeString: string) => {
  try {
    const date = new Date(timeString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return timeString
  }
}

const getCountdownValue = (expireTime: string) => {
  try {
    return new Date(expireTime).getTime()
  } catch {
    return Date.now()
  }
}

const getActivityTimeStatus = (expireTime: string): 'normal' | 'warning' | 'ended' => {
  try {
    const expire = new Date(expireTime)
    const now = new Date()
    const remaining = expire.getTime() - now.getTime()
    const twoDaysInMs = 2 * 24 * 60 * 60 * 1000
    if (remaining <= 0) return 'ended'
    if (remaining <= twoDaysInMs) return 'warning'
    return 'normal'
  } catch {
    return 'ended'
  }
}

const onCountdownFinish = () => {
  message.warning('活动已结束')
  fetchActivityData()
}

const getMaterialImage = (dropName: string) => {
  if (!dropName) {
    return ''
  }
  return `${OpenAPI.BASE}/api/res/materials/${dropName}.png`
}

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

const fetchSchedulerTaskOptions = async (options?: { quiet?: boolean }) => {
  schedulerTasksLoading.value = true

  try {
    const response = await Service.getTaskComboxApiInfoComboxTaskPost()
    if (response.code === 200 && response.data?.length) {
      schedulerTaskOptions.value = response.data
      if (
        !selectedHomeTaskId.value ||
        !response.data.some(item => item.value === selectedHomeTaskId.value)
      ) {
        selectedHomeTaskId.value = response.data[0]?.value ?? null
      }
      return
    }

    schedulerTaskOptions.value = mockSchedulerTasks
    selectedHomeTaskId.value = mockSchedulerTasks[0]?.value ?? null
    if (!options?.quiet) {
      message.warning('任务列表暂不可用，已显示占位任务')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`获取首页任务列表失败: ${errorMsg}`)
    schedulerTaskOptions.value = mockSchedulerTasks
    selectedHomeTaskId.value = mockSchedulerTasks[0]?.value ?? null
  } finally {
    schedulerTasksLoading.value = false
  }
}

const onSchedulerDropdownVisibleChange = (open: boolean) => {
  if (open) {
    fetchSchedulerTaskOptions({ quiet: true })
  }
}

const startHomeTask = async () => {
  if (!selectedHomeTaskId.value) {
    message.error('请选择任务项')
    return
  }

  if (selectedHomeTaskId.value.startsWith('mock-')) {
    message.info('当前为首页占位任务，接入真实任务列表后可直接启动')
    return
  }

  startingHomeTask.value = true
  try {
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: selectedHomeTaskId.value,
      mode: selectedHomeMode.value,
    })

    if (response.code === 200) {
      message.success('任务已开始')
      await playSound('task_started')
    } else {
      message.error(response.message || '开始任务失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`首页开始任务失败: ${errorMsg}`)
    message.error('开始任务失败，请检查调度服务状态')
  } finally {
    startingHomeTask.value = false
  }
}

const fetchActivityData = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await Service.getOverviewApiInfoGetOverviewPost()

    if (response.code === 200) {
      const data = response.data as ApiResponse
      if (data.Stage) {
        activityData.value = data.Stage.Activity || []
        resourceData.value = data.Stage.Resource || []
      }
      if (data.Proxy) {
        proxyData.value = data.Proxy
      }
    } else {
      error.value = response.message || '获取数据失败'
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    logger.error(`获取数据失败: ${errorMsg}`)
    error.value = '网络请求失败，请检查连接'
  } finally {
    loading.value = false
  }
}

const fetchNoticeData = async () => {
  try {
    const response = await Service.getNoticeInfoApiInfoNoticeGetPost()

    if (response.code === 200) {
      if (response.if_need_show && response.data && Object.keys(response.data).length > 0) {
        noticeData.value = response.data
        noticeVisible.value = true
        await playSound('announcement_display')
      }
    } else {
      logger.warn(`获取公告失败: ${response.message}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取公告失败: ${errorMsg}`)
  } finally {
    noticeLoading.value = false
  }
}

const onNoticeConfirmed = () => {
  noticeVisible.value = false
}

const showNotice = async () => {
  noticeLoading.value = true
  try {
    const response = await Service.getNoticeInfoApiInfoNoticeGetPost()

    if (response.code === 200) {
      if (response.data && Object.keys(response.data).length > 0) {
        noticeData.value = response.data
        noticeVisible.value = true
        await playSound('announcement_display')
      } else {
        message.info('暂无公告信息')
      }
    } else {
      message.error(response.message || '获取公告失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`显示公告失败: ${errorMsg}`)
    message.error('显示公告失败，请稍后重试')
  } finally {
    noticeLoading.value = false
  }
}

const loadHomeData = () => {
  fetchSchedulerTaskOptions({ quiet: true })
  fetchActivityData()
  fetchNoticeData()
}

onMounted(() => {
  loadHomeLayoutConfig()

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

.home-subtitle {
  color: var(--ant-color-text-secondary);
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
  margin-top: 0px;
  width: 100%;
}

.home-module {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.module-editor-bar {
  min-height: 40px;
  padding: 7px 10px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.module-editor-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.module-editor-extra {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.module-editor-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.module-editor-extra + .module-editor-actions {
  margin-left: 0;
}

.command-card,
.shortcut-card,
.proxy-card,
.activity-card,
.resource-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.command-card :deep(.ant-card-body) {
  padding: 24px;
}

.shortcut-card :deep(.ant-card-body) {
  padding: 0;
}

.shortcut-card :deep(.ant-card-head-title),
.proxy-card :deep(.ant-card-head-title),
.activity-card :deep(.ant-card-head-title),
.resource-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.command-panel {
  min-height: 148px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 24px;
  color: var(--ant-color-text);
}

.command-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.command-kicker {
  width: fit-content;
  margin-bottom: 10px;
  color: var(--ant-color-primary);
  font-size: 12px;
  font-weight: 600;
}

.command-title {
  font-size: 30px;
  line-height: 1.2;
  font-weight: 700;
  color: var(--ant-color-text);
}

.command-meta {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.command-meta span {
  padding-right: 12px;
  color: var(--ant-color-text-secondary);
  border-right: 1px solid var(--ant-color-border);
  font-size: 13px;
}

.command-meta span:last-child {
  border-right: none;
}

.scheduler-launcher {
  min-width: 0;
  padding: 0 0 0 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border-left: 1px solid var(--ant-color-border);
}

.launcher-header {
  margin-bottom: 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.launcher-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.launcher-subtitle {
  margin-top: 2px;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
}

.launcher-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 112px;
  gap: 12px;
}

.launcher-select,
.launcher-start {
  width: 100%;
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
}

.quick-action {
  min-height: 108px;
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  text-align: left;
  color: var(--ant-color-text);
  background: transparent;
  border: none;
  border-right: 1px solid var(--ant-color-border-secondary);
  cursor: pointer;
  transition:
    color 0.16s ease,
    transform 0.16s ease;
}

.quick-action:last-child {
  border-right: none;
}

.quick-action:hover {
  color: var(--ant-color-primary);
  transform: translateY(-1px);
}

.quick-action:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.quick-action-icon {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 42px;
  color: var(--ant-color-primary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  font-size: 20px;
}

.quick-action-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.quick-action-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.quick-action-desc {
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
  white-space: normal;
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
  align-items: start;
}

.proxy-card {
  width: 100%;
}

.arknights-collapse {
  background: transparent;
  border-radius: 8px;
}

.arknights-collapse :deep(.ant-collapse-content-box) {
  padding: 18px 0 0;
}

.arknights-collapse :deep(.ant-collapse-header) {
  align-items: center;
  font-size: 16px;
  font-weight: 600;
}

.activity-card {
  margin-bottom: 16px;
}

.resource-card {
  margin-bottom: 0;
}

.resource-list {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}

.resource-item,
.activity-item {
  min-height: 82px;
  display: flex;
  align-items: center;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.resource-item:hover,
.activity-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.drop-tip {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin-top: 2px;
}

.error-message {
  margin-bottom: 16px;
}

.activity-info {
  margin-bottom: 24px;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.activity-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.activity-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.activity-right {
  flex-shrink: 0;
  text-align: right;
}

.activity-end-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.activity-name {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.activity-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.time-icon {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.time-label {
  color: var(--ant-color-text-secondary);
  min-width: 80px;
}

.time-value {
  color: var(--ant-color-text);
  font-weight: 500;
}

.activity-list {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stage-info {
  flex: 1;
  margin-right: 16px;
  text-align: center;
  min-width: 50px;
  max-width: 80px;
}

.stage-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 4px;
}

.drop-info {
  display: flex;
  align-items: center;
  flex: 2;
  min-width: 0;
}

.drop-image {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  overflow: hidden;
}

.drop-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.drop-details {
  flex: 1;
  min-width: 70px;
}

.drop-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  margin-bottom: 4px;
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 40px 0;
}

.empty-image {
  max-width: 180px;
  width: 48%;
  opacity: 0.82;
}

.proxy-list .proxy-item {
  min-height: 164px;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.proxy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.proxy-username {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-icon {
  color: var(--ant-color-text-secondary);
}

.username {
  min-width: 0;
  font-weight: 600;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.proxy-stats {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.stat-item.full-width {
  grid-column: 1 / -1;
}

.stat-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.rainbow-text {
  font-weight: bold;
  font-size: 18px;
  background: linear-gradient(270deg, #ff4d4f, #fffa00, #00ffea, #ff4d4f, #ff4d4f);
  background-size: 400% 400%;
  color: transparent;
  background-clip: text;
  -webkit-background-clip: text;
  animation: rainbow-move 4s linear infinite;
}

@keyframes rainbow-move {
  0% {
    background-position: 0 50%;
  }

  100% {
    background-position: 100% 50%;
  }
}

@media (max-width: 1500px) {
  .activity-list,
  .resource-list {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 1240px) {
  .command-panel {
    grid-template-columns: 1fr;
  }

  .scheduler-launcher {
    max-width: 100%;
    padding: 18px 0 0;
    border-left: none;
    border-top: 1px solid var(--ant-color-border);
  }

  .quick-actions {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .quick-action:nth-child(3n) {
    border-right: none;
  }

  .quick-action:nth-child(n + 4) {
    border-top: 1px solid var(--ant-color-border-secondary);
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .activity-list,
  .resource-list {
    grid-template-columns: repeat(3, 1fr);
  }
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

  .command-card :deep(.ant-card-body) {
    padding: 18px;
  }

  .command-title {
    font-size: 24px;
  }

  .quick-actions,
  .activity-list,
  .resource-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .quick-action:nth-child(2n) {
    border-right: none;
  }

  .quick-action:nth-child(3n) {
    border-right: 1px solid var(--ant-color-border-secondary);
  }

  .quick-action:nth-child(n + 3) {
    border-top: 1px solid var(--ant-color-border-secondary);
  }

  .activity-header {
    flex-direction: column;
  }

  .activity-right {
    text-align: left;
  }
}

@media (max-width: 560px) {
  .launcher-controls {
    grid-template-columns: 1fr;
  }

  .quick-actions,
  .activity-list,
  .resource-list {
    grid-template-columns: 1fr;
  }

  .quick-action {
    min-height: 82px;
    border-right: none;
    border-top: 1px solid var(--ant-color-border-secondary);
  }

  .quick-action:nth-child(3n) {
    border-right: none;
  }

  .quick-action:first-child {
    border-top: none;
  }

  .stat-pair {
    grid-template-columns: 1fr;
  }
}
</style>
