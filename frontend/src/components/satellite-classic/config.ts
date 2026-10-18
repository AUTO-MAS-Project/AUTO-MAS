/** 场景尺寸与动画参数；长度是 three.js 世界单位，相机在 500 处，约 1.18 单位对应 1 像素 */
export const SATELLITE_CONFIG = {
  containerHeight: 400,
  orbitRadiusX: 400,
  orbitRadiusY: 170,
  orbitTilt: 0.35,
  orbitOpacity: 0.4,
  centerCardSize: 90,
  satelliteCardSize: 60,
  /**
   * 图标面朝镜头前移的距离。卡片以前是有厚度的立方体，正面在厚度一半处；
   * 现在只画正面，留着这个偏移让画面和以前一致。
   */
  centerCardFaceOffset: 5,
  satelliteCardFaceOffset: 4,
  satelliteOrbitSpeed: 0.0006,
  satelliteFloatAmplitude: 10,
  satelliteFloatSpeed: 1.2,
  centerFloatAmplitude: 4,
  centerFloatSpeed: 0.8,
  cameraFov: 50,
  cameraY: 80,
  cameraZ: 500,
  cardAppearDelay: 150,
  cardAppearDuration: 400,
  glowSizeMultiplier: 3.5,
  activityGlowZOffset: -5,
  errorGlowZOffset: -3,
} as const

export const SATELLITE_COLORS = {
  /** 排队、运行中的光晕，也是中心图标平时的光晕 */
  active: 0x6ce08a,
  /** 上次失败 */
  failed: 0xff5a5f,
  /** 上次失败、这次又在跑 */
  failedRunning: 0xffc247,
  explosionFlash: 0x8ce7ff,
  explosionRing: 0x6ce0ff,
  orbitDark: 0x555555,
  orbitLight: 0xbbbbbb,
} as const

/** 中心图标按下去时的形变，照 dsh-whale-widget 的 SQUISH 加大幅度：压扁、横向撑开 */
export const CENTER_PRESS_SCALE_X = 1.15
export const CENTER_PRESS_SCALE_Y = 0.75
