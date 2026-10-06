import { useI18n } from 'vue-i18n'
import { createCenterPokeCounter } from './centerPoke'
import { createDizzyDetector, createKonamiMatcher, maaPokeTally } from './eggs'
import type { FloatTextVariant } from './floatText'
import type { SatelliteScene, ScreenPoint } from './satelliteScene'

interface SatelliteEggsOptions {
  /** 场景还没建好或已经销毁时返回 null */
  getScene: () => SatelliteScene | null
  isLowPower: () => boolean
  /** 在卫星容器里 point 处冒一句字 */
  spawnText: (point: ScreenPoint, text: string, variant: FloatTextVariant) => void
  /** 卫星容器的尺寸，周哥的大字摆在底部居中 */
  getContainerSize: () => { width: number; height: number } | null
  requestRender: () => void
}

/**
 * 主页卫星的彩蛋：中心连点炫彩、MAA 点满 325 下周哥出场、科乐美秘技超频、来回猛搓转晕。
 * 长按星核放冲击波是指针手势的一部分，留在组件里。
 */
export function useSatelliteEggs(options: SatelliteEggsOptions) {
  const { getScene, isLowPower, spawnText, getContainerSize, requestRender } = options
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('卫星动画')
  const centerPoke = createCenterPokeCounter()
  const konami = createKonamiMatcher()
  const dizzyDetector = createDizzyDetector()

  /** 点了一下中心图标：连点 5 次起按概率换成炫彩图标，30 次保底 */
  function pokeCenter(): void {
    const scene = getScene()
    // 低性能模式下彩虹不会流动，触发了也只是一张静止的图，不给机会
    if (!scene || isLowPower()) return

    const hit = centerPoke.poke(performance.now(), scene.isCenterRainbow)
    if (!hit) return
    scene.setCenterRainbow(true)
    logger.info(hit === 'guarantee' ? '中心图标彩蛋触发：连点保底' : '中心图标彩蛋触发：炫彩图标')
  }

  /** 点了一下第 index 颗卫星；只有 MAA 计数 */
  function pokeSatellite(index: number): void {
    const scene = getScene()
    if (!scene || scene.satelliteType(index) !== 'MAA') return

    const event = maaPokeTally.poke()
    if (!event) return

    if (event.kind !== 'reveal') {
      const point = scene.projectSatellite(index)
      const text =
        event.kind === 'hint' ? t(`home.satelliteEgg.${event.hint}`) : String(event.remaining)
      if (point) spawnText(point, text, 'hint')
      return
    }

    void scene.revealZhouge(index)
    // 等脸飞到镜头前再出大字
    window.setTimeout(() => {
      const size = getContainerSize()
      if (!getScene() || !size) return
      spawnText({ x: size.width / 2, y: size.height * 0.86 }, t('home.satelliteEgg.zhouge'), 'huge')
    }, 650)
    logger.info('卫星彩蛋触发：MAA 点满 325 下，周哥出场')
  }

  function isEditableTarget(target: EventTarget | null): boolean {
    return (
      target instanceof HTMLElement &&
      (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
    )
  }

  /** ↑↑↓↓←→←→BA 开超频；在输入框里打字不算 */
  function handleKeydown(event: KeyboardEvent): void {
    const scene = getScene()
    if (!scene || isLowPower() || isEditableTarget(event.target)) return
    if (!konami.feed(event.key)) return

    scene.startOverclock(Date.now())
    spawnText(scene.projectCenter(), t('home.satelliteEgg.overclock'), 'huge')
    logger.info('卫星彩蛋触发：科乐美秘技超频')
    requestRender()
  }

  /** 每帧喂一次镜头转速：拖着星系来回猛搓会转晕 */
  function checkDizzy(dt: number, now: number): void {
    const scene = getScene()
    if (!scene || isLowPower() || !dizzyDetector.feed(scene.spinSpeed, dt, now)) return

    scene.startDizzy(now)
    spawnText(scene.projectCenter(), t('home.satelliteEgg.dizzy'), 'hint')
    logger.info('卫星彩蛋触发：转晕')
  }

  return { pokeCenter, pokeSatellite, handleKeydown, checkDizzy }
}
