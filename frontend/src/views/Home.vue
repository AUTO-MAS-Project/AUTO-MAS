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
          :class="{
            'is-editing': layoutEditing,
            'is-hidden': layoutEditing && !isHomeModuleShown(moduleKey),
          }"
        >
          <div v-if="layoutEditing" class="module-editor-bar">
            <div class="module-editor-title">{{ moduleTitleMap[moduleKey] }}</div>
            <div class="module-editor-options">
              <div class="module-editor-option">
                <span>展示</span>
                <a-switch
                  size="small"
                  :checked="isHomeModuleShown(moduleKey)"
                  @change="setHomeModuleShown(moduleKey, $event)"
                />
              </div>
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
                <!--                <BlurReveal-->
                <!--                  v-if="!isBootstrapping"-->
                <!--                  :text="commandTitle"-->
                <!--                  class="command-title"-->
                <!--                  :delay="0.15"-->
                <!--                  :duration="0.8"-->
                <!--                />-->

                <EncryptedText
                  v-if="!isBootstrapping"
                  :text="commandTitle"
                  class="command-title"
                  encrypted-class="command-title-encrypted"
                  :reveal-delay-ms="66"
                  :flip-delay-ms="500"
                />
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
import EncryptedText from '@/components/inspira/EncryptedText.vue'
import NoticeModal from '@/components/NoticeModal.vue'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useAppInitialization } from '@/composables/useAppInitialization'
import SatelliteAnimation from '@/components/SatelliteAnimation.vue'
import type { ComboBoxItem } from '@/api'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import { navigateTo } from '@/router'
defineOptions({
  name: 'HomeView',
})

const logger = window.electronAPI.getLogger('首页')

interface ProxyInfo {
  LastProxyDate: string
  ProxyTimes: number
  ErrorTimes: number
  ErrorInfo: Record<string, any>
}

interface ApiResponse {
  Proxy: Record<string, ProxyInfo>
}

type HomeModuleKey = 'command' | 'quick' | 'satellite' | 'proxy'
type HomeModuleDirection = 'up' | 'down'

interface HomeLayoutConfig {
  moduleOrder: HomeModuleKey[]
  hiddenModules: HomeModuleKey[]
}

const HOME_LAYOUT_STORAGE_KEY = 'auto-mas.home.layout'
const defaultHomeModuleOrder: HomeModuleKey[] = ['command', 'quick', 'satellite', 'proxy']
const moduleTitleMap: Record<HomeModuleKey, string> = {
  command: '快速开始',
  quick: '常用入口',
  satellite: '卫星环绕',
  proxy: '代理状态',
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

const homeGreetingMessages = [
  '坐和放宽，脚本正在为你努力运行中。',
  '启动前请确认脚本路径已正确，否则它将无法找到自己。',
  '请勿™强制关闭AUTO-MAS，正在处理一些事情。',
  '好东西就要来了……别来无恙啊！',
  'AUTO-MAS正在为你的设备匹配专属脚本设置。',
  '启动AUTO-MAS脚本系统，不要说我们没有警告过你。',
  '需要重启脚本是正常现象，请不要惊慌。',
  '你的设备正在准备就绪，准备好迎接脚本运行了吗？',
  '运行完成后，你的游戏进度可能会发生位移。',
  '我们的脚本协议更新了，你只能同意不能不同意。',
  '请耐心等待，进度条只是看起来不动而已。',
  '感谢你使用AUTO-MAS，你永远可以相信脚本的力量。',
  '正在应用最适合当前宇宙版本的脚本设置。',
  '你的请求很重要，AUTO-MAS正在以看似安静的方式处理它。',
  'AUTO-MAS检测到一切正常，除非稍后它不正常。',
  '请稍候，系统正在把复杂问题包装成一个按钮。',
]

const pickHomeGreeting = () => {
  const index = Math.floor(Math.random() * homeGreetingMessages.length)
  return homeGreetingMessages[index] ?? homeGreetingMessages[0]
}

const loading = ref(false)
const schedulerTasksLoading = ref(false)
const startingHomeTask = ref(false)
const layoutEditing = ref(false)
const homeModuleOrder = ref<HomeModuleKey[]>([...defaultHomeModuleOrder])
const hiddenHomeModules = ref<HomeModuleKey[]>([])
const proxyData = ref<Record<string, ProxyInfo>>({})
const schedulerTaskOptions = ref<ComboBoxItem[]>(mockSchedulerTasks)
const selectedHomeTaskId = ref<string | null>(mockSchedulerTasks[0]?.value ?? null)
const selectedHomeMode = ref<TaskCreateIn.mode>(TaskCreateIn.mode.AUTO_PROXY)

const noticeVisible = ref(false)
const noticeData = ref<Record<string, string>>({})
const noticeLoading = ref(false)
const { isBootstrapping } = useAppInitialization()
const { playSound } = useAudioPlayer()
const commandTitle = ref(pickHomeGreeting())

const isHomeModuleKey = (value: unknown): value is HomeModuleKey => {
  return typeof value === 'string' && defaultHomeModuleOrder.includes(value as HomeModuleKey)
}

const normalizeHomeModuleOrder = (order: unknown): HomeModuleKey[] => {
  const configuredOrder = Array.isArray(order) ? order.filter(isHomeModuleKey) : []
  const uniqueOrder = configuredOrder.filter((key, index, array) => array.indexOf(key) === index)
  const missingOrder = defaultHomeModuleOrder.filter(key => !uniqueOrder.includes(key))
  return [...uniqueOrder, ...missingOrder]
}

const normalizeHomeHiddenModules = (hiddenModules: unknown): HomeModuleKey[] => {
  const configuredHiddenModules = Array.isArray(hiddenModules)
    ? hiddenModules.filter(isHomeModuleKey)
    : []
  return configuredHiddenModules.filter((key, index, array) => array.indexOf(key) === index)
}

const persistHomeLayoutConfig = () => {
  try {
    const config: HomeLayoutConfig = {
      moduleOrder: homeModuleOrder.value,
      hiddenModules: hiddenHomeModules.value,
    }
    localStorage.setItem(HOME_LAYOUT_STORAGE_KEY, JSON.stringify(config))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`保存首页布局配置失败: ${errorMsg}`)
  }
}

const loadHomeLayoutConfig = () => {
  try {
    const rawConfig = localStorage.getItem(HOME_LAYOUT_STORAGE_KEY)
    if (rawConfig) {
      const config = JSON.parse(rawConfig) as Partial<HomeLayoutConfig>
      homeModuleOrder.value = normalizeHomeModuleOrder(config.moduleOrder)
      hiddenHomeModules.value = normalizeHomeHiddenModules(config.hiddenModules)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取首页布局配置失败: ${errorMsg}`)
  }
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

const isHomeModuleShown = (key: HomeModuleKey) => {
  return !hiddenHomeModules.value.includes(key)
}

const setHomeModuleShown = (key: HomeModuleKey, checked: boolean | string | number) => {
  const shouldShow = Boolean(checked)
  if (shouldShow) {
    hiddenHomeModules.value = hiddenHomeModules.value.filter(hiddenKey => hiddenKey !== key)
  } else if (!hiddenHomeModules.value.includes(key)) {
    hiddenHomeModules.value = [...hiddenHomeModules.value, key]
  }
  persistHomeLayoutConfig()
}

const isHomeModuleVisible = (key: HomeModuleKey) => {
  return layoutEditing.value || isHomeModuleShown(key)
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

const fetchOverviewData = async () => {
  loading.value = true

  try {
    const response = await Service.getOverviewApiInfoGetOverviewPost()

    if (response.code === 200) {
      const data = response.data as ApiResponse
      if (data.Proxy) {
        proxyData.value = data.Proxy
      }
    } else {
      logger.warn(`获取首页概览失败: ${response.message || '获取数据失败'}`)
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    logger.error(`获取首页概览失败: ${errorMsg}`)
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
  fetchOverviewData()
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

.module-editor-options {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.module-editor-option {
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

.module-editor-options + .module-editor-actions {
  margin-left: 0;
}

.home-module.is-hidden > :not(.module-editor-bar) {
  opacity: 0.42;
  filter: grayscale(0.18);
}

.command-card,
.shortcut-card,
.proxy-card {
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
.proxy-card :deep(.ant-card-head-title) {
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

.command-title :deep(.command-title-encrypted) {
  color: var(--ant-color-text-secondary);
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

  .quick-actions {
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
}

@media (max-width: 560px) {
  .launcher-controls {
    grid-template-columns: 1fr;
  }

  .quick-actions {
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
