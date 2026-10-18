import { useI18n } from 'vue-i18n'
import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import type { ScriptType } from '@/types/script'
import { createCenterPokeCounter } from './centerPoke'
import {
  consumeFirstLaunch,
  createCodeMatcher,
  createDizzyDetector,
  createKonamiMatcher,
  createRapidClickDetector,
  KEY_CODES,
  keyOfEvent,
  pokePity,
  type KeyCode,
  type PityReward,
} from './eggs'
import type { FloatTextVariant } from './floatText'
import type { SatelliteScene, ScreenPoint } from './satelliteScene'

/** 彩蛋舞台（SatelliteEggStage）对外的三个大场面 */
export interface SatelliteEggStageApi {
  showPolaroid(src: string): void
  launchGenshin(): void
  launchRockets(): Promise<void>
}

interface SatelliteEggsOptions {
  /** 场景还没建好或已经销毁时返回 null */
  getScene: () => SatelliteScene | null
  getStage: () => SatelliteEggStageApi | null
  /** 在卫星容器里 point 处冒一句字 */
  spawnText: (point: ScreenPoint, text: string, variant: FloatTextVariant) => void
  /** 卫星容器的尺寸，彩蛋大字摆在底部居中 */
  getContainerSize: () => { width: number; height: number } | null
  /** 暴雨期间给画面上一层老照片的色调 */
  setStormTint: (on: boolean) => void
  requestRender: () => void
}

/** 出金的颜色：原神、星铁、鸣潮金色，方舟系六星橙色，绝区零 S 级琥珀，蔚蓝档案出彩 */
const REWARD_COLORS: Record<Exclude<PityReward, 'zhouge'>, number> = {
  gold: 0xffcf5a,
  sixStar: 0xff9a3c,
  sRank: 0xffb000,
  spark: 0xff8fd6,
}
/** 金色流星从天上落下来砸中卫星要这么久，大字等砸中再出 */
const GOLD_IMPACT_MS = 750
const STORM_TINT_MS = 6500
/** 鼠标在 MAA 上停这么久，阿米娅开口 */
const AMIYA_HOVER_MS = 6000
const AMIYA_COOLDOWN_MS = 60000
const BANGBOO_LINES = 3
const WISH_LINES = 4

/**
 * 主页卫星的彩蛋。点卫星攒保底出金、MAA 点满 325 下周哥出场、BGI 连点 5 下原神启动、
 * 星铁连点 7 下三月七拍照、绝区零每点一下邦布回话、鼠标停在 MAA 上阿米娅催你干活、
 * 脚本开跑时喊一句启动、中心连点炫彩、点流星许愿、键盘口令（科乐美秘技、648、1999、
 * 666、520、404、233、mas）、来回猛搓转晕。长按星核放冲击波是指针手势的一部分，留在组件里。
 */
export function useSatelliteEggs(options: SatelliteEggsOptions) {
  const { getScene, getStage, spawnText, requestRender } = options
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('卫星动画')
  const centerPoke = createCenterPokeCounter()
  const konami = createKonamiMatcher()
  const codes = createCodeMatcher(KEY_CODES)
  const dizzyDetector = createDizzyDetector()
  const genshinRapid = createRapidClickDetector(5, 3000, 15000)
  const photoRapid = createRapidClickDetector(7, 3000, 8000)
  const timers = new Set<number>()
  let amiyaTimer: number | null = null
  let lastAmiyaAt = -Infinity
  /** 上一次看到在跑的卫星键 */
  let runningKeys: Set<string> | null = null

  function later(callback: () => void, ms: number): number {
    const timer = window.setTimeout(() => {
      timers.delete(timer)
      callback()
    }, ms)
    timers.add(timer)
    return timer
  }

  function pick<T>(items: readonly T[]): T {
    return items[Math.floor(Math.random() * items.length)]
  }

  /** 卫星容器底部居中冒一句大字 */
  function spawnBanner(text: string, delay = 0): void {
    later(() => {
      const size = options.getContainerSize()
      if (!getScene() || !size) return
      spawnText({ x: size.width / 2, y: size.height * 0.86 }, text, 'huge')
    }, delay)
  }

  function spawnNearSatellite(index: number, text: string, variant: FloatTextVariant): void {
    const point = getScene()?.projectSatellite(index)
    if (point) spawnText(point, text, variant)
  }

  // ==================== 点击 ====================

  /** 点了一下中心图标：连点 5 次起按概率换成炫彩图标，30 次保底 */
  function pokeCenter(): void {
    const scene = getScene()
    if (!scene) return

    const hit = centerPoke.poke(performance.now(), scene.isCenterRainbow)
    if (!hit) return
    scene.setCenterRainbow(true)
    logger.info(hit === 'guarantee' ? '中心图标彩蛋触发：连点保底' : '中心图标彩蛋触发：炫彩图标')
  }

  /** 点了一下第 index 颗卫星 */
  function pokeSatellite(index: number): void {
    const scene = getScene()
    const type = scene?.satelliteType(index)
    if (!scene || !type) return
    const now = performance.now()

    if (type === 'ZzzOd') {
      // 邦布只会说「嗯呢」
      spawnNearSatellite(
        index,
        t(`home.satelliteEgg.bangboo${1 + Math.floor(Math.random() * BANGBOO_LINES)}`),
        'hint'
      )
    }
    if (type === 'BetterGI' && genshinRapid.click(now)) {
      getStage()?.launchGenshin()
      logger.info('卫星彩蛋触发：BGI 连点 5 下，原神启动')
    }
    if ((type === 'SRC' || type === 'HSR') && photoRapid.click(now)) {
      takePhoto(index)
    }

    handlePity(index, type)
  }

  /** 三月七的相机：咔嚓一声，把当前画面做成拍立得 */
  function takePhoto(index: number): void {
    const snapshot = getScene()?.captureSnapshot()
    if (!snapshot) return
    getStage()?.showPolaroid(snapshot)
    spawnNearSatellite(index, t('home.satelliteEgg.shutter'), 'hint')
    logger.info('卫星彩蛋触发：星铁连点 7 下，三月七拍照')
  }

  function handlePity(index: number, type: ScriptType): void {
    const scene = getScene()
    const event = pokePity(type)
    if (!scene || !event) return

    if (event.kind === 'hint') {
      spawnNearSatellite(index, t(`home.satelliteEgg.${event.key}`), 'hint')
      return
    }
    if (event.kind === 'countdown') {
      spawnNearSatellite(index, String(event.remaining), 'hint')
      return
    }

    if (event.reward === 'zhouge') {
      void scene.revealZhouge(index)
      // 等脸飞到镜头前再出大字
      spawnBanner(t('home.satelliteEgg.zhouge'), 650)
      logger.info('卫星彩蛋触发：MAA 点满 325 下，周哥出场')
      return
    }

    scene.playGoldPull(index, Date.now(), REWARD_COLORS[event.reward], event.reward === 'spark')
    spawnBanner(t(`home.satelliteEgg.${event.reward}`), GOLD_IMPACT_MS)
    requestRender()
    logger.info(`卫星彩蛋触发：${type} 攒满保底，出金`)
  }

  /** 按下的地方没有卫星和中心图标时试试接流星；接住了就许个愿，返回 true */
  function tryCatchMeteor(clientX: number, clientY: number): boolean {
    const scene = getScene()
    if (!scene) return false
    const point = scene.catchMeteor(clientX, clientY, Date.now())
    if (!point) return false
    spawnText(
      point,
      t(`home.satelliteEgg.wish${1 + Math.floor(Math.random() * WISH_LINES)}`),
      'hint'
    )
    requestRender()
    logger.info('卫星彩蛋触发：流星许愿')
    return true
  }

  // ==================== 悬停与状态 ====================

  /** 鼠标在 MAA 上停住不动 6 秒，阿米娅提醒博士还不能休息 */
  function onHoverChange(index: number | null): void {
    if (amiyaTimer !== null) {
      window.clearTimeout(amiyaTimer)
      timers.delete(amiyaTimer)
      amiyaTimer = null
    }
    if (index === null || getScene()?.satelliteType(index) !== 'MAA') return

    amiyaTimer = later(() => {
      amiyaTimer = null
      const now = performance.now()
      if (now - lastAmiyaAt < AMIYA_COOLDOWN_MS) return
      lastAmiyaAt = now
      spawnNearSatellite(index, t('home.satelliteEgg.amiya'), 'speech')
      logger.info('卫星彩蛋触发：阿米娅')
    }, AMIYA_HOVER_MS)
  }

  /**
   * 脚本开跑时在它的卫星旁喊一句「××，启动！」（BGI 是「原神，启动！」）；
   * 每个脚本每次启动应用只喊一次。刚挂载时已经在跑的不算，只认看着它开跑的那一下。
   */
  function onStatusesChange(statuses: ReadonlyMap<string, SatelliteModuleStatus>): void {
    const scene = getScene()
    const running = new Set(
      [...statuses].filter(([, status]) => status.running).map(([key]) => key)
    )
    const previous = runningKeys
    runningKeys = running
    if (!scene || !previous) return

    for (const key of running) {
      if (previous.has(key) || !consumeFirstLaunch(key)) continue
      const index = scene.findSatellite(key)
      if (index === null) continue
      const text =
        scene.satelliteType(index) === 'BetterGI'
          ? t('home.satelliteEgg.genshinLaunch')
          : t('home.satelliteEgg.launch', { name: scene.satelliteLabel(index) })
      spawnNearSatellite(index, text, 'hint')
    }
  }

  // ==================== 键盘 ====================

  function isEditableTarget(target: EventTarget | null): boolean {
    return (
      target instanceof HTMLElement &&
      (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
    )
  }

  /** 在输入框里打字不算 */
  function handleKeydown(event: KeyboardEvent): void {
    const scene = getScene()
    if (!scene || isEditableTarget(event.target)) return

    const key = keyOfEvent(event)
    if (konami.feed(key)) {
      scene.startOverclock(Date.now())
      spawnText(scene.projectCenter(), t('home.satelliteEgg.overclock'), 'huge')
      logger.info('卫星彩蛋触发：科乐美秘技超频')
      requestRender()
      return
    }

    const code = codes.feed(key)
    if (code) {
      playCode(code)
      logger.info(`卫星彩蛋触发：口令 ${code}`)
      requestRender()
    }
  }

  function playCode(code: KeyCode): void {
    const scene = getScene()
    if (!scene) return
    const now = Date.now()
    const center = scene.projectCenter()

    switch (code) {
      case '648':
        scene.playCrystalRain(now)
        spawnBanner(t('home.satelliteEgg.topUp'))
        break
      case '1999':
        scene.startStorm(now)
        options.setStormTint(true)
        later(() => options.setStormTint(false), STORM_TINT_MS)
        spawnBanner(t('home.satelliteEgg.storm'))
        break
      case '666':
        scene.playFireworks(now)
        spawnBanner('666', 300)
        break
      case '520':
        scene.playHearts(now)
        spawnText(center, '520', 'love')
        break
      case '404':
        scene.vanish(now)
        spawnBanner(t('home.satelliteEgg.notFound'), 450)
        break
      case '233':
        for (let i = 0; i < 6; i++) {
          later(() => {
            const size = options.getContainerSize()
            if (!size) return
            spawnText(
              {
                x: size.width * (0.2 + Math.random() * 0.6),
                y: size.height * (0.35 + Math.random() * 0.4),
              },
              pick(['233', '2333', '233333', t('home.satelliteEgg.laugh')]),
              'hint'
            )
          }, i * 140)
        }
        break
      case 'mas':
        void getStage()?.launchRockets()
        break
    }
  }

  // ==================== 拖动 ====================

  /** 每帧喂一次镜头转速：拖着星系来回猛搓会转晕 */
  function checkDizzy(dt: number, now: number): void {
    const scene = getScene()
    if (!scene || !dizzyDetector.feed(scene.spinSpeed, dt, now)) return

    scene.startDizzy(now)
    spawnText(scene.projectCenter(), t('home.satelliteEgg.dizzy'), 'hint')
    logger.info('卫星彩蛋触发：转晕')
  }

  function dispose(): void {
    timers.forEach(timer => window.clearTimeout(timer))
    timers.clear()
    amiyaTimer = null
    options.setStormTint(false)
  }

  return {
    pokeCenter,
    pokeSatellite,
    tryCatchMeteor,
    onHoverChange,
    onStatusesChange,
    handleKeydown,
    checkDizzy,
    dispose,
  }
}
