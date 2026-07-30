<template>
  <section ref="panel" class="satellite-panel" aria-labelledby="satellite-panel-title">
    <header class="satellite-panel__header">
      <div>
        <h2 id="satellite-panel-title" class="satellite-panel__title">专项脚本卫星</h2>
        <p class="satellite-panel__description">按脚本类型汇总运行状态</p>
      </div>
      <a-tag v-if="statusStale" color="gold">状态已过期</a-tag>
    </header>

    <a-alert
      v-if="moduleError && hasVisibleModules"
      class="satellite-panel__alert"
      type="warning"
      show-icon
      message="专项脚本列表刷新失败，正在显示上次结果"
      :description="moduleError"
    >
      <template #action>
        <a-button size="small" :loading="loadingModules" @click="loadModules">重试</a-button>
      </template>
    </a-alert>

    <a-alert
      v-if="moduleWarning && hasVisibleModules"
      class="satellite-panel__alert"
      type="warning"
      show-icon
      message="部分专项脚本未显示"
      :description="moduleWarning"
    >
      <template #action>
        <a-button size="small" :loading="loadingModules" @click="loadModules">重试</a-button>
      </template>
    </a-alert>

    <div v-if="loadingModules && !hasVisibleModules" class="satellite-panel__state">
      <a-spin size="large" tip="正在加载专项脚本…" />
    </div>

    <a-result
      v-else-if="moduleError && !hasVisibleModules"
      class="satellite-panel__state"
      status="error"
      title="无法加载专项脚本卫星"
      :sub-title="moduleError"
    >
      <template #extra>
        <a-button type="primary" :loading="loadingModules" @click="loadModules">重新加载</a-button>
      </template>
    </a-result>

    <div v-else-if="!hasVisibleModules" class="satellite-panel__state">
      <a-empty :description="emptyDescription" />
    </div>

    <template v-else>
      <div ref="sceneViewport" class="satellite-panel__scene" aria-hidden="true"></div>

      <a-alert
        v-if="statusError"
        class="satellite-panel__alert satellite-panel__status-alert"
        :type="hasStatusSnapshot ? 'warning' : 'error'"
        show-icon
        :message="hasStatusSnapshot ? '状态刷新失败，正在显示上次结果' : '暂时无法获取运行状态'"
        :description="statusError"
      >
        <template #action>
          <a-button size="small" :loading="statusRefreshing" @click="retryStatuses">
            重试
          </a-button>
        </template>
      </a-alert>

      <div class="satellite-panel__status-area" aria-live="polite">
        <ul class="satellite-status-list" aria-label="专项脚本类型状态">
          <li v-for="row in statusRows" :key="row.typeKey" class="satellite-status-item">
            <span
              class="satellite-status-dot"
              :class="`satellite-status-dot--${row.visualState}`"
              aria-hidden="true"
            ></span>
            <span class="satellite-status-item__name" :title="row.displayName">
              {{ row.displayName }}
              <span class="satellite-status-item__count">×{{ row.instanceCount }}</span>
            </span>
            <a-tag :color="row.meta.color">{{ row.meta.label }}</a-tag>
          </li>
        </ul>

        <div class="satellite-legend" aria-label="状态图例">
          <span v-for="item in legendItems" :key="item.state" class="satellite-legend__item">
            <span
              class="satellite-status-dot"
              :class="`satellite-status-dot--${item.state}`"
              aria-hidden="true"
            ></span>
            {{ item.label }}
          </span>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Service } from '@/api'
import centerIconUrl from '@/assets/satellite-icons/AUTO-MAS.png'
import { useWebSocket } from '@/composables/useWebSocket'
import { onConnected } from '@/services/websocket/connection'
import { WS_ID_PLUGIN_SYSTEM, WS_PLUGIN_SNAPSHOT_UPDATED } from '@/services/websocket/types'
import {
  getSatelliteModules,
  getSatelliteModuleStatuses,
  type SatelliteModule,
  type SatelliteVisualStatus,
} from '@/composables/useSatelliteStatus'
import { useTheme } from '@/composables/useTheme'
import {
  loadSatelliteIconCanvas,
  SatelliteAnimationScene,
  type PreparedSatelliteModule,
} from '@/components/satellite-animation/scene'
import {
  SATELLITE_LEGEND_ITEMS,
  SATELLITE_STATUS_META,
} from '@/components/satellite-animation/presentation'

const logger = window.electronAPI.getLogger('卫星动画')

const STATUS_UPDATE_INTERVAL = 10_000
const MAX_VISIBLE_SATELLITES = 12

const legendItems = SATELLITE_LEGEND_ITEMS

const panel = ref<HTMLElement | null>(null)
const sceneViewport = ref<HTMLDivElement | null>(null)
const loadingModules = ref(true)
const moduleError = ref<string | null>(null)
const moduleWarning = ref<string | null>(null)
const hasSpecializedInstances = ref(false)
const visibleModules = ref<SatelliteModule[]>([])
const visualStatuses = ref<Map<string, SatelliteVisualStatus>>(new Map())
const hasStatusSnapshot = ref(false)
const statusError = ref<string | null>(null)
const statusRefreshing = ref(false)

const { isDark } = useTheme()
const { subscribe, unsubscribe } = useWebSocket()

const hasVisibleModules = computed(() => visibleModules.value.length > 0)
const statusStale = computed(() => hasStatusSnapshot.value && statusError.value !== null)
const emptyDescription = computed(() =>
  hasSpecializedInstances.value ? '暂无带有效图标的专项脚本' : '暂无已配置的专项脚本'
)
const statusRows = computed(() =>
  visibleModules.value.map(module => {
    const visualState = visualStatuses.value.get(module.typeKey) ?? 'unknown'
    return {
      ...module,
      visualState,
      meta: SATELLITE_STATUS_META[visualState],
    }
  })
)

let scene: SatelliteAnimationScene | null = null
let animationFrameId: number | null = null
let statusTimer: number | null = null
let statusRequestInFlight = false
let moduleRequestId = 0
let statusGeneration = 0
let isUnmounted = false
let isDocumentVisible = true
let isPanelVisible = false
let prefersReducedMotion = false
let intersectionObserver: IntersectionObserver | null = null
let resizeObserver: ResizeObserver | null = null
let reducedMotionQuery: MediaQueryList | null = null
let pluginSystemSubscriptionId: string | null = null
let disposeConnectionRefresh: (() => void) | null = null

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function canRun(): boolean {
  return scene !== null && hasVisibleModules.value && isDocumentVisible && isPanelVisible
}

function clearStatusTimer(): void {
  if (statusTimer !== null) {
    window.clearTimeout(statusTimer)
    statusTimer = null
  }
}

function stopAnimation(): void {
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

function pauseWork(): void {
  stopAnimation()
  clearStatusTimer()
  scene?.pauseMotion()
}

function renderStatic(): void {
  if (!scene || !isDocumentVisible || !isPanelVisible) return
  scene.render(performance.now(), false, prefersReducedMotion)
}

function startAnimation(): void {
  if (!canRun() || prefersReducedMotion || animationFrameId !== null) return

  const step = (timestamp: number) => {
    if (!canRun() || prefersReducedMotion) {
      animationFrameId = null
      return
    }
    scene?.render(timestamp, true)
    animationFrameId = requestAnimationFrame(step)
  }
  animationFrameId = requestAnimationFrame(step)
}

function scheduleStatusRefresh(): void {
  clearStatusTimer()
  if (!canRun()) return
  statusTimer = window.setTimeout(() => {
    statusTimer = null
    void refreshStatuses()
  }, STATUS_UPDATE_INTERVAL)
}

async function refreshStatuses(): Promise<void> {
  if (!canRun() || statusRequestInFlight) return

  const requestGeneration = statusGeneration
  statusRequestInFlight = true
  statusRefreshing.value = true
  try {
    const statuses = await getSatelliteModuleStatuses()
    if (isUnmounted || requestGeneration !== statusGeneration) return

    const nextStatuses = new Map<string, SatelliteVisualStatus>()
    visibleModules.value.forEach(module => {
      nextStatuses.set(module.typeKey, statuses.get(module.typeKey)?.visualState ?? 'unknown')
    })
    visualStatuses.value = nextStatuses
    hasStatusSnapshot.value = true
    statusError.value = null
    scene?.setStatuses(nextStatuses)
    if (prefersReducedMotion) {
      renderStatic()
    }
  } catch (error) {
    if (!isUnmounted && requestGeneration === statusGeneration) {
      statusError.value = errorMessage(error, '状态刷新失败')
      logger.warn(`刷新卫星状态失败：${statusError.value}`)
    }
  } finally {
    statusRequestInFlight = false
    statusRefreshing.value = false
    if (!isUnmounted && requestGeneration === statusGeneration) {
      scheduleStatusRefresh()
    } else if (!isUnmounted && canRun()) {
      void refreshStatuses()
    }
  }
}

function retryStatuses(): void {
  clearStatusTimer()
  void refreshStatuses()
}

function resumeWork(): void {
  if (!canRun()) return
  clearStatusTimer()
  if (prefersReducedMotion) {
    stopAnimation()
    renderStatic()
  } else {
    startAnimation()
  }
  void refreshStatuses()
}

function disposeScene(): void {
  pauseWork()
  statusGeneration += 1
  resizeObserver?.disconnect()
  scene?.dispose()
  scene = null
}

async function prepareModules(
  modules: SatelliteModule[]
): Promise<{ prepared: PreparedSatelliteModule[]; failures: string[] }> {
  const failures: string[] = []
  const results = await Promise.all(
    modules.map(async module => {
      try {
        const iconCanvas = await loadSatelliteIconCanvas(module.iconUrl)
        return { module, iconCanvas }
      } catch (error) {
        failures.push(module.displayName)
        logger.warn(
          `跳过图标无效的专项脚本类型 ${module.typeKey}：${errorMessage(error, '未知错误')}`
        )
        return null
      }
    })
  )
  return {
    prepared: results.filter((item): item is PreparedSatelliteModule => item !== null),
    failures,
  }
}

async function loadModules(): Promise<void> {
  const requestId = ++moduleRequestId
  loadingModules.value = true
  moduleError.value = null
  moduleWarning.value = null
  pauseWork()

  try {
    const discovery = await getSatelliteModules()
    const selectedModules = discovery.modules.slice(0, MAX_VISIBLE_SATELLITES)
    const { prepared: preparedModules, failures } = await prepareModules(selectedModules)
    const centerIconCanvas =
      preparedModules.length > 0 ? await loadSatelliteIconCanvas(centerIconUrl) : null

    if (isUnmounted || requestId !== moduleRequestId) return

    hasSpecializedInstances.value = discovery.hasSpecializedInstances
    const warnings: string[] = []
    if (discovery.modules.length > MAX_VISIBLE_SATELLITES) {
      warnings.push(`专项脚本类型超过展示上限，仅显示前 ${MAX_VISIBLE_SATELLITES} 个`)
    }
    if (failures.length > 0) {
      warnings.push(`以下类型的图标加载失败：${failures.join('、')}`)
    }

    if (preparedModules.length === 0 || !centerIconCanvas) {
      disposeScene()
      hasStatusSnapshot.value = false
      statusError.value = null
      visualStatuses.value = new Map()
      visibleModules.value = []
      if (discovery.modules.length > 0) {
        moduleError.value = warnings.join('；') || '专项脚本图标加载失败'
      }
      return
    }

    await nextTick()
    if (isUnmounted || requestId !== moduleRequestId) return
    if (!sceneViewport.value) {
      throw new Error('卫星场景容器不可用')
    }

    const candidateScene = new SatelliteAnimationScene(
      sceneViewport.value,
      centerIconCanvas,
      preparedModules,
      isDark.value
    )
    if (isUnmounted || requestId !== moduleRequestId) {
      candidateScene.dispose()
      return
    }

    const previousScene = scene
    scene = candidateScene
    previousScene?.dispose()
    hasStatusSnapshot.value = false
    statusError.value = null
    visualStatuses.value = new Map()
    visibleModules.value = preparedModules.map(item => item.module)
    moduleWarning.value = warnings.join('；') || null
    resizeObserver?.observe(sceneViewport.value)
    resumeWork()
    void updateCenterGlowMode()
  } catch (error) {
    if (!isUnmounted && requestId === moduleRequestId) {
      moduleError.value = errorMessage(error, '加载专项脚本失败')
      logger.error(`加载卫星模块失败：${moduleError.value}`)
      resumeWork()
    }
  } finally {
    if (!isUnmounted && requestId === moduleRequestId) {
      loadingModules.value = false
    }
  }
}

async function updateCenterGlowMode(): Promise<void> {
  const version = import.meta.env.VITE_APP_VERSION || '1.0.0'
  try {
    const response = await Service.checkUpdateApiUpdateCheckPost({
      current_version: version,
      if_force: false,
    })
    if (response.code === 200 && response.if_need_update) {
      scene?.setCenterGlowMode('rainbow')
      if (prefersReducedMotion) {
        renderStatic()
      }
    }
  } catch {
    // 更新检查不影响卫星展示。
  }
}

function handleActivityChange(): void {
  if (canRun()) {
    resumeWork()
  } else {
    pauseWork()
  }
}

function handleVisibilityChange(): void {
  isDocumentVisible = !document.hidden
  handleActivityChange()
}

function handleReducedMotionChange(event: MediaQueryListEvent): void {
  prefersReducedMotion = event.matches
  handleActivityChange()
}

watch(isDark, value => {
  scene?.updateTheme(value)
  if (prefersReducedMotion) {
    renderStatic()
  }
})

onMounted(() => {
  isUnmounted = false
  isDocumentVisible = !document.hidden
  document.addEventListener('visibilitychange', handleVisibilityChange)

  reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  prefersReducedMotion = reducedMotionQuery.matches
  reducedMotionQuery.addEventListener('change', handleReducedMotionChange)

  if ('IntersectionObserver' in window) {
    intersectionObserver = new IntersectionObserver(
      entries => {
        isPanelVisible = entries.some(entry => entry.isIntersecting)
        handleActivityChange()
      },
      { threshold: 0.05 }
    )
    if (panel.value) {
      intersectionObserver.observe(panel.value)
    }
  } else {
    isPanelVisible = true
  }

  resizeObserver = new ResizeObserver(() => {
    scene?.resize()
    if (prefersReducedMotion) {
      renderStatic()
    }
  })

  pluginSystemSubscriptionId = subscribe(
    { id: WS_ID_PLUGIN_SYSTEM, type: WS_PLUGIN_SNAPSHOT_UPDATED },
    () => void loadModules()
  )
  disposeConnectionRefresh = onConnected(() => void loadModules())
  void loadModules()
})

onUnmounted(() => {
  isUnmounted = true
  moduleRequestId += 1
  disposeScene()
  intersectionObserver?.disconnect()
  resizeObserver?.disconnect()
  if (pluginSystemSubscriptionId) {
    unsubscribe(pluginSystemSubscriptionId)
    pluginSystemSubscriptionId = null
  }
  disposeConnectionRefresh?.()
  disposeConnectionRefresh = null
  reducedMotionQuery?.removeEventListener('change', handleReducedMotionChange)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style scoped src="./satellite-animation/styles.css"></style>
