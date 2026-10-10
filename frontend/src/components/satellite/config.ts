/** 场景尺寸与动画参数；长度是 three.js 世界单位 */
export const SATELLITE_CONFIG = {
  /** 长焦：透视收敛一些，前后卫星的大小差在两倍左右，近处的不至于糊到镜头上 */
  cameraFov: 24,
  /**
   * 镜头离星核的基准距离；容器太窄时会自动拉远，保证主轨道左右不出画。
   * 轨道要斜到把星核整个圈住，上下得留出余量，所以比原先的 1130 远一些（卫星区相应加高）。
   */
  cameraDistance: 1210,
  /** 镜头默认俯视角（弧度） */
  cameraElevation: 0.14,
  cameraElevationMin: -0.05,
  cameraElevationMax: 0.6,
  /**
   * 镜头注视点低于星核。俯视时轨道离镜头近的半圈会被透视往下拉，
   * 不往下看一点，近处的卫星会顶到容器底边。
   */
  cameraTargetY: -60,
  /** 鼠标视差：指针移到容器边缘时镜头最多偏转的角度 */
  parallaxYaw: 0.14,
  parallaxPitch: 0.06,

  centerCardSize: 96,
  coreShellRadius: 70,

  satelliteSize: 70,
  satelliteDepth: 8,
  /** 轨道基础角速度（弧度/毫秒），内圈按开普勒规律转得更快 */
  orbitSpeed: 0.00042,
  satelliteFloatAmplitude: 6,
  satelliteFloatSpeed: 1.2,
  centerFloatAmplitude: 4,
  centerFloatSpeed: 0.8,
  /** 卫星绕自身的摆动幅度（弧度），露出方块的厚度和金属边 */
  satelliteWobble: 0.42,

  cardAppearDelay: 150,
  cardAppearDuration: 700,
  glowSizeMultiplier: 3.2,

  trailLength: 44,
  /** 彗尾相邻两点在轨道上相隔的角度 */
  trailSpacing: 0.011,
  starCount: 520,
  swirlCount: 260,
} as const

/**
 * 轨道：先绕 x 轴倾斜 tiltX，再绕视线（z 轴）转 tiltZ。两条内圈斜着交叉，像原子模型。
 *
 * 每条都斜到在画面上把星核整个圈住：默认视角加上鼠标视差、镜头慢摇的范围内，
 * 卫星都不会从星核前面压过去（orbitClearance.test.ts 钉住）。拖动转视角时仍可能经过，停手转回正面就好。
 */
export interface OrbitRing {
  radius: number
  tiltX: number
  tiltZ: number
}

export const ORBIT_RINGS: readonly OrbitRing[] = [
  { radius: 430, tiltX: 0.26, tiltZ: 0 },
  { radius: 270, tiltX: 0.5, tiltZ: 0.3 },
  { radius: 310, tiltX: 0.42, tiltZ: -0.2 },
]

export const SATELLITE_COLORS = {
  /** 排队、运行中的光晕，也是中心图标平时的光晕 */
  active: 0x6ce08a,
  /** 上次失败 */
  failed: 0xff5a5f,
  /** 上次失败、这次又在跑 */
  failedRunning: 0xffc247,
  explosionFlash: 0x8ce7ff,
  explosionRing: 0x6ce0ff,
  orbitDark: 0x6f8fb3,
  orbitLight: 0x8a9bb0,
  trailDark: 0x7fd3ff,
  trailLight: 0x3f7fd6,
  tileDark: 0x1a2130,
  tileLight: 0xf3f6fb,
  gyroDark: 0x63e6ff,
  gyroLight: 0x2f8fd8,
} as const

/** 中心图标按下去时的形变，照 dsh-whale-widget 的 SQUISH 加大幅度：压扁、横向撑开 */
export const CENTER_PRESS_SCALE_X = 1.15
export const CENTER_PRESS_SCALE_Y = 0.75

/** 长按星核：按住超过 chargeStart 开始蓄力，满 chargeFull 松手放冲击波 */
export const CORE_CHARGE = {
  chargeStart: 450,
  chargeFull: 1300,
} as const
