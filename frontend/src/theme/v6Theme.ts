export const V6_UI_SCALE_MIN = 0.8
export const V6_UI_SCALE_MAX = 1.4
export const V6_UI_SCALE_DEFAULT = 1

export interface V6ThemePalette {
  layout: string
  container: string
  elevated: string
  titlebar: string
  sidebar: string
  text: string
  textSecondary: string
  textTertiary: string
  border: string
  borderSecondary: string
  success: string
  warning: string
  error: string
  info: string
}

export const V6_THEME_PALETTES: Record<'light' | 'dark', V6ThemePalette> = {
  light: {
    layout: '#f5f5f7',
    container: '#ffffff',
    elevated: '#ffffff',
    titlebar: 'rgb(246 246 248 / 88%)',
    sidebar: 'rgb(242 242 247 / 86%)',
    text: 'rgba(29, 29, 31, 0.92)',
    textSecondary: 'rgba(29, 29, 31, 0.66)',
    textTertiary: 'rgba(29, 29, 31, 0.46)',
    border: 'rgba(0, 0, 0, 0.1)',
    borderSecondary: 'rgba(0, 0, 0, 0.06)',
    success: '#34c759',
    warning: '#ff9f0a',
    error: '#ff3b30',
    info: '#007aff',
  },
  dark: {
    layout: '#1e1e1e',
    container: '#28282a',
    elevated: '#2c2c2e',
    titlebar: 'rgb(32 32 34 / 90%)',
    sidebar: 'rgb(38 38 40 / 88%)',
    text: 'rgba(245, 245, 247, 0.92)',
    textSecondary: 'rgba(245, 245, 247, 0.66)',
    textTertiary: 'rgba(245, 245, 247, 0.46)',
    border: 'rgba(255, 255, 255, 0.1)',
    borderSecondary: 'rgba(255, 255, 255, 0.06)',
    success: '#30d158',
    warning: '#ff9f0a',
    error: '#ff453a',
    info: '#0a84ff',
  },
}

const roundScale = (value: number) => Math.round(value * 20) / 20

export const normalizeUiScale = (value: unknown): number => {
  if (value === null || value === undefined || value === '') return V6_UI_SCALE_DEFAULT
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return V6_UI_SCALE_DEFAULT
  return roundScale(Math.min(V6_UI_SCALE_MAX, Math.max(V6_UI_SCALE_MIN, parsed)))
}

export const buildV6ThemeCssVariables = (dark: boolean, scale: unknown): Record<string, string> => {
  const palette = V6_THEME_PALETTES[dark ? 'dark' : 'light']
  const normalizedScale = normalizeUiScale(scale)

  // vibrancy 表面：与 v6-tokens.css 中 :root / :root.dark 中的语义保持一致，
  // 在运行时随主题切换同步覆盖，保证 light/dark 与 isDark 状态严格对齐。
  const vibrancy = dark
    ? {
        '--v6-vibrancy-sidebar': 'rgb(38 38 40 / 80%)',
        '--v6-vibrancy-titlebar': 'rgb(32 32 34 / 75%)',
        '--v6-vibrancy-toolbar': 'rgb(36 36 38 / 70%)',
        '--v6-vibrancy-content': 'rgb(40 40 42 / 60%)',
        '--v6-vibrancy-popover': 'rgb(50 50 52 / 85%)',
        '--v6-vibrancy-hover': 'rgb(255 255 255 / 6%)',
        '--v6-vibrancy-selected': 'rgb(10 132 255 / 28%)',
        '--v6-vibrancy-active': '#0a84ff',
      }
    : {
        '--v6-vibrancy-sidebar': 'rgb(242 242 247 / 80%)',
        '--v6-vibrancy-titlebar': 'rgb(246 246 248 / 72%)',
        '--v6-vibrancy-toolbar': 'rgb(247 247 249 / 70%)',
        '--v6-vibrancy-content': 'rgb(255 255 255 / 65%)',
        '--v6-vibrancy-popover': 'rgb(255 255 255 / 85%)',
        '--v6-vibrancy-hover': 'rgb(0 0 0 / 6%)',
        '--v6-vibrancy-selected': 'rgb(0 122 255 / 18%)',
        '--v6-vibrancy-active': '#007aff',
      }

  return {
    '--v6-ui-scale': String(normalizedScale),
    '--v6-color-window': palette.layout,
    '--v6-color-surface': palette.container,
    '--v6-color-surface-elevated': palette.elevated,
    '--v6-color-titlebar': palette.titlebar,
    '--v6-color-sidebar': palette.sidebar,
    '--v6-color-border': palette.border,
    '--v6-color-border-subtle': palette.borderSecondary,
    '--v6-color-text': palette.text,
    '--v6-color-text-secondary': palette.textSecondary,
    '--v6-color-text-tertiary': palette.textTertiary,
    '--v6-color-success': palette.success,
    '--v6-color-warning': palette.warning,
    '--v6-color-error': palette.error,
    '--v6-color-info': palette.info,
    ...vibrancy,
  }
}

/**
 * 性能模式：'low' 关闭 vibrancy 滤镜/阴影/动效；'normal' 保持设计意图。
 * 由 useTheme.ts 读取 localStorage('perf-mode') 决定，缺省时调用 detectLowPerfMode()。
 */
export type V6PerfMode = 'low' | 'normal'

/**
 * 低性能模式硬件检测上下文。抽象为接口以便单元测试注入 mock。
 */
export interface V6PerfDetectionContext {
  hardwareConcurrency?: number
  deviceMemory?: number
  prefersReducedMotion?: boolean
}

/**
 * 纯函数：根据硬件能力 + 系统偏好判定是否启用低性能模式。
 * - navigator.hardwareConcurrency < 4 → 视为低性能
 * - navigator.deviceMemory < 4 (GB) → 视为低性能
 * - matchMedia('(prefers-reduced-motion: reduce)').matches → 视为低性能
 * 任一命中即返回 'low'，否则 'normal'。
 *
 * 缺失字段（如 deviceMemory 在部分浏览器不可用）跳过该项判定，不视为命中。
 */
export const detectLowPerfMode = (context: V6PerfDetectionContext = {}): V6PerfMode => {
  const { hardwareConcurrency, deviceMemory, prefersReducedMotion } = context

  if (
    typeof hardwareConcurrency === 'number' &&
    hardwareConcurrency > 0 &&
    hardwareConcurrency < 4
  ) {
    return 'low'
  }
  if (typeof deviceMemory === 'number' && deviceMemory > 0 && deviceMemory < 4) {
    return 'low'
  }
  if (prefersReducedMotion === true) {
    return 'low'
  }
  return 'normal'
}

/**
 * 从浏览器运行时收集硬件检测上下文。在非浏览器环境（SSR/测试）下安全返回空对象，
 * 调用方得到 'normal' 默认值。
 */
export const collectPerfDetectionContext = (): V6PerfDetectionContext => {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return {}
  }

  const context: V6PerfDetectionContext = {}

  const hc = (navigator as Navigator & { hardwareConcurrency?: number }).hardwareConcurrency
  if (typeof hc === 'number') {
    context.hardwareConcurrency = hc
  }

  const dm = (navigator as Navigator & { deviceMemory?: number }).deviceMemory
  if (typeof dm === 'number') {
    context.deviceMemory = dm
  }

  try {
    if (typeof window.matchMedia === 'function') {
      context.prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    }
  } catch {
    // matchMedia 在某些隐私模式下可能抛错，忽略该项。
  }

  return context
}

export const buildV6AntThemeTokens = (dark: boolean, primaryColor: string, scale: unknown) => {
  const palette = V6_THEME_PALETTES[dark ? 'dark' : 'light']
  const normalizedScale = normalizeUiScale(scale)

  return {
    colorPrimary: primaryColor,
    colorInfo: palette.info,
    colorSuccess: palette.success,
    colorWarning: palette.warning,
    colorError: palette.error,
    colorBgLayout: palette.layout,
    colorBgContainer: palette.container,
    colorBgElevated: palette.elevated,
    colorText: palette.text,
    colorTextSecondary: palette.textSecondary,
    colorTextTertiary: palette.textTertiary,
    colorBorder: palette.border,
    colorBorderSecondary: palette.borderSecondary,
    fontFamily:
      '"Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
    fontFamilyCode: '"Cascadia Mono", "SF Mono", Consolas, ui-monospace, monospace',
    fontSize: Math.round(14 * normalizedScale),
    controlHeight: Math.round(32 * normalizedScale),
    borderRadius: Math.round(6 * normalizedScale),
    borderRadiusLG: Math.round(12 * normalizedScale),
    motionDurationFast: '0.15s',
    motionDurationMid: '0.25s',
    motionDurationSlow: '0.35s',
    motionEaseOut: 'cubic-bezier(0.32, 0.72, 0, 1)',
    boxShadow: '0 1px 3px rgb(0 0 0 / 5%)',
    boxShadowSecondary: dark ? '0 8px 28px rgb(0 0 0 / 36%)' : '0 8px 28px rgb(0 0 0 / 12%)',
  }
}
