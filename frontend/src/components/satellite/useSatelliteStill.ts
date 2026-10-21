import { ref } from 'vue'
import { centerIconUrl } from '@/composables/satellite-config'
import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import type { CenterGlowMode } from './motion'
import { SatelliteScene, type SatelliteSceneModule } from './satelliteScene'

/** 状态、主题、尺寸变化后隔这么久重拍；连着变只拍最后一次 */
const STILL_REFRESH_DELAY = 400
/** 静态图定格的时刻，取一个卫星散得开、镜头摆正的瞬间 */
const STILL_TIME = 1_000_000

interface SatelliteStillOptions {
  getContainer: () => HTMLElement | null
  getModules: () => readonly SatelliteSceneModule[] | null
  getStatuses: () => ReadonlyMap<string, SatelliteModuleStatus>
  getCenterGlowMode: () => CenterGlowMode
  isDark: () => boolean
  /** 这次拍摄还该不该继续（卸载了、退出低性能模式了就不该） */
  isWanted: () => boolean
}

/**
 * 低性能模式的静态图：临时搭一个场景，定格画一帧导出成图片，随即销毁。
 * 页面上只留这张图，不跑动画、不占着 WebGL；状态、主题、尺寸变了再重拍一张。
 */
export function useSatelliteStill(options: SatelliteStillOptions) {
  const logger = window.electronAPI.getLogger('卫星动画')
  const image = ref<string | null>(null)
  let token = 0
  let timer: number | null = null

  function cancelScheduled(): void {
    if (timer === null) return
    window.clearTimeout(timer)
    timer = null
  }

  /** 拍一张；新的一次开始时，还没拍完的旧一次作废 */
  async function render(): Promise<void> {
    cancelScheduled()
    const current = ++token
    const container = options.getContainer()
    const modules = options.getModules()
    if (!container || !modules) return

    const still = new SatelliteScene(container, { isDark: options.isDark() })
    try {
      const loaded = await still.load(
        centerIconUrl,
        modules,
        () => current !== token || !options.isWanted()
      )
      if (!loaded) return
      still.setStatuses(options.getStatuses())
      still.setCenterGlowMode(options.getCenterGlowMode())
      still.skipAppear()
      image.value = still.renderStill(STILL_TIME)
    } catch (err) {
      logger.warn(`生成卫星静态图失败: ${String(err)}`)
    } finally {
      still.dispose()
    }
  }

  /** 稍后重拍；只在需要静态图的时候生效 */
  function schedule(): void {
    if (!options.isWanted()) return
    cancelScheduled()
    timer = window.setTimeout(() => {
      timer = null
      void render()
    }, STILL_REFRESH_DELAY)
  }

  /** 不要静态图了：作废还在拍的、清掉已有的 */
  function clear(): void {
    cancelScheduled()
    token += 1
    image.value = null
  }

  return { image, render, schedule, clear }
}
