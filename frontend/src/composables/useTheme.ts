import { theme } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

export type ThemeMode = 'system' | 'light' | 'dark'
export type ThemeColor =
  | 'blue'
  | 'purple'
  | 'cyan'
  | 'green'
  | 'magenta'
  | 'pink'
  | 'red'
  | 'orange'
  | 'yellow'
  | 'volcano'
  | 'geekblue'
  | 'lime'
  | 'gold'

const themeMode = ref<ThemeMode>('system')
const themeColor = ref<ThemeColor>('blue')
const isDark = ref(false)

// 预设主题色
const themeColors: Record<ThemeColor, string> = {
  blue: '#1677ff',
  purple: '#722ed1',
  cyan: '#13c2c2',
  green: '#52c41a',
  magenta: '#eb2f96',
  pink: '#eb2f96',
  red: '#ff4d4f',
  orange: '#fa8c16',
  yellow: '#fadb14',
  volcano: '#fa541c',
  geekblue: '#2f54eb',
  lime: '#a0d911',
  gold: '#faad14',
}

// 检测系统主题
const getSystemTheme = () => {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

// 更新TDesign主题
const updateTDesignTheme = (isDarkMode: boolean) => {
  // 设置TDesign的主题模式
  const htmlElement = document.documentElement

  if (isDarkMode) {
    // 添加TDesign深色主题类名
    htmlElement.setAttribute('theme-mode', 'dark')
  } else {
    // 设置为浅色主题
    htmlElement.setAttribute('theme-mode', 'light')
  }
}
// 更新主题
const updateTheme = () => {
  let shouldBeDark: boolean

  if (themeMode.value === 'system') {
    shouldBeDark = getSystemTheme()
  } else {
    shouldBeDark = themeMode.value === 'dark'
  }

  isDark.value = shouldBeDark

  // 更新HTML类名
  if (shouldBeDark) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }

  // 更新TDesign主题
  updateTDesignTheme(shouldBeDark)

  // 更新CSS变量
  updateCSSVariables()
}

// 更新CSS变量
const updateCSSVariables = () => {
  const root = document.documentElement
  const primaryColor = themeColors[themeColor.value]

  // 基础背景（用于估算混合）
  const baseLightBg = '#ffffff'
  const baseDarkBg = '#141414'
  const baseMenuBg = isDark.value ? baseDarkBg : baseLightBg

  // 改进：侧边栏背景使用 HSL 调整而不是简单线性混合，提高在不同主色下的可读性
  const siderBg = deriveSiderBg(primaryColor, baseMenuBg, isDark.value)
  const siderBorder = deriveSiderBorder(siderBg, primaryColor, isDark.value)

  // 基础文字候选色
  const candidateTextLight = 'rgba(255,255,255,0.88)'
  const candidateTextDark = 'rgba(0,0,0,0.88)'

  // 选菜单文字颜色：对 siderBg 计算对比度，优先满足 >=4.5
  const menuTextColor = pickAccessibleColor(candidateTextDark, candidateTextLight, siderBg)
  const iconColor = menuTextColor

  // ===== AntD token 变量（保留） =====
  if (isDark.value) {
    root.style.setProperty('--ant-color-primary', primaryColor)
    root.style.setProperty('--ant-color-primary-hover', hslLighten(primaryColor, 6))
    root.style.setProperty('--ant-color-primary-bg', addAlpha(primaryColor, 0.1))
    root.style.setProperty('--ant-color-text', 'rgba(255, 255, 255, 0.88)')
    root.style.setProperty('--ant-color-text-secondary', 'rgba(255, 255, 255, 0.65)')
    root.style.setProperty('--ant-color-text-tertiary', 'rgba(255, 255, 255, 0.45)')
    root.style.setProperty('--ant-color-bg-container', baseDarkBg)
    root.style.setProperty('--ant-color-bg-layout', '#000000')
    root.style.setProperty('--ant-color-bg-elevated', '#1f1f1f')
    root.style.setProperty('--ant-color-border', '#424242')
    root.style.setProperty('--ant-color-border-secondary', '#303030')
    root.style.setProperty('--ant-color-error', '#ff4d4f')
    root.style.setProperty('--ant-color-success', '#52c41a')
    root.style.setProperty('--ant-color-warning', '#faad14')
  } else {
    root.style.setProperty('--ant-color-primary', primaryColor)
    root.style.setProperty('--ant-color-primary-hover', hslDarken(primaryColor, 6))
    root.style.setProperty('--ant-color-primary-bg', addAlpha(primaryColor, 0.1))
    root.style.setProperty('--ant-color-text', 'rgba(0, 0, 0, 0.88)')
    root.style.setProperty('--ant-color-text-secondary', 'rgba(0, 0, 0, 0.65)')
    root.style.setProperty('--ant-color-text-tertiary', 'rgba(0, 0, 0, 0.45)')
    root.style.setProperty('--ant-color-bg-container', baseLightBg)
    root.style.setProperty('--ant-color-bg-layout', '#f5f5f5')
    root.style.setProperty('--ant-color-bg-elevated', '#ffffff')
    root.style.setProperty('--ant-color-border', '#d9d9d9')
    root.style.setProperty('--ant-color-border-secondary', '#d9d9d9')
    root.style.setProperty('--ant-color-error', '#ff4d4f')
    root.style.setProperty('--ant-color-success', '#52c41a')
    root.style.setProperty('--ant-color-warning', '#faad14')
  }

  // ===== 自定义菜单配色 =====
  // 动态 Alpha：根据主色亮度调整透明度以保持区分度
  const lumPrim = getLuminance(primaryColor)
  const hoverAlphaBase = isDark.value ? 0.22 : 0.14
  const selectedAlphaBase = isDark.value ? 0.38 : 0.26
  const hoverAlpha = clamp01(
    hoverAlphaBase + (isDark.value ? (lumPrim > 0.65 ? -0.04 : 0) : lumPrim < 0.3 ? 0.04 : 0)
  )
  const selectedAlpha = clamp01(
    selectedAlphaBase + (isDark.value ? (lumPrim > 0.65 ? -0.05 : 0) : lumPrim < 0.3 ? 0.05 : 0)
  )

  // 估算最终选中背景（混合算实际颜色用于对比度计算）
  const estimatedSelectedBg = blendColors(baseMenuBg, primaryColor, selectedAlpha)
  const selectedTextColor = pickAccessibleColor(
    'rgba(0,0,0,0.90)',
    'rgba(255,255,255,0.92)',
    estimatedSelectedBg
  )
  const hoverTextColor = menuTextColor

  root.style.setProperty('--app-sider-bg', siderBg)
  root.style.setProperty('--app-sider-border-color', siderBorder)
  root.style.setProperty('--app-menu-text-color', menuTextColor)
  root.style.setProperty('--app-menu-icon-color', iconColor)
  root.style.setProperty('--app-menu-item-hover-text-color', hoverTextColor)
  root.style.setProperty('--app-menu-item-selected-text-color', selectedTextColor)

  // 背景同时提供 rgba 与 hex alpha（兼容处理）
  const hoverRgba = hexToRgba(primaryColor, hoverAlpha)
  const selectedRgba = hexToRgba(primaryColor, selectedAlpha)
  root.style.setProperty('--app-menu-item-hover-bg', hoverRgba)
  root.style.setProperty('--app-menu-item-hover-bg-hex', addAlpha(primaryColor, hoverAlpha))
  root.style.setProperty('--app-menu-item-selected-bg', selectedRgba)
  root.style.setProperty('--app-menu-item-selected-bg-hex', addAlpha(primaryColor, selectedAlpha))
}

// ===== 新增缺失基础函数（从旧版本恢复） =====
const addAlpha = (hex: string, alpha: number) => {
  const a = alpha > 1 ? alpha / 100 : alpha
  const clamped = Math.min(1, Math.max(0, a))
  const alphaHex = Math.round(clamped * 255)
    .toString(16)
    .padStart(2, '0')
  return `${hex}${alphaHex}`
}

const blendColors = (color1: string, color2: string, ratio: number) => {
  const r1 = hexToRgb(color1)
  const r2 = hexToRgb(color2)
  if (!r1 || !r2) return color1
  const r = Math.round(r1.r * (1 - ratio) + r2.r * ratio)
  const g = Math.round(r1.g * (1 - ratio) + r2.g * ratio)
  const b = Math.round(r1.b * (1 - ratio) + r2.b * ratio)
  return rgbToHex(r, g, b)
}

const getLuminance = (hex: string) => {
  const rgb = hexToRgb(hex)
  if (!rgb) return 0
  const transform = (v: number) => {
    const srgb = v / 255
    return srgb <= 0.03928 ? srgb / 12.92 : Math.pow((srgb + 0.055) / 1.055, 2.4)
  }
  const r = transform(rgb.r)
  const g = transform(rgb.g)
  const b = transform(rgb.b)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

// ===== 新增/改进的颜色工具 =====
const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

const hexToRgb = (hex: string) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : null
}

const rgbToHex = (r: number, g: number, b: number) => {
  return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)
}

// 新增：hex -> rgba 字符串
const hexToRgba = (hex: string, alpha: number) => {
  const rgb = hexToRgb(hex)
  if (!rgb) return 'rgba(0,0,0,0)'
  const a = alpha > 1 ? alpha / 100 : alpha
  return `rgba(${rgb.r},${rgb.g},${rgb.b},${clamp01(a)})`
}

// HSL 转换（感知更平滑）
const rgbToHsl = (r: number, g: number, b: number) => {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b),
    min = Math.min(r, g, b)
  let h = 0,
    s = 0
  const l = (max + min) / 2
  const d = max - min
  if (d !== 0) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0)
        break
      case g:
        h = (b - r) / d + 2
        break
      case b:
        h = (r - g) / d + 4
        break
    }
    h /= 6
  }
  return { h: h * 360, s, l }
}

const hslToRgb = (h: number, s: number, l: number) => {
  h /= 360
  if (s === 0) {
    const val = Math.round(l * 255)
    return { r: val, g: val, b: val }
  }
  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1
    if (t > 1) t -= 1
    if (t < 1 / 6) return p + (q - p) * 6 * t
    if (t < 1 / 2) return q
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
    return p
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  const r = hue2rgb(p, q, h + 1 / 3)
  const g = hue2rgb(p, q, h)
  const b = hue2rgb(p, q, h - 1 / 3)
  return { r: Math.round(r * 255), g: Math.round(g * 255), b: Math.round(b * 255) }
}

const hslAdjust = (hex: string, dl: number) => {
  const rgb = hexToRgb(hex)
  if (!rgb) return hex
  const { h, s, l } = rgbToHsl(rgb.r, rgb.g, rgb.b)
  const nl = clamp01(l + dl)
  const nrgb = hslToRgb(h, s, nl)
  return rgbToHex(nrgb.r, nrgb.g, nrgb.b)
}

const hslLighten = (hex: string, percent: number) => hslAdjust(hex, percent / 100)
const hslDarken = (hex: string, percent: number) => hslAdjust(hex, -percent / 100)

// 对比度 (WCAG)
const contrastRatio = (hex1: string, hex2: string) => {
  const L1 = getLuminance(hex1)
  const L2 = getLuminance(hex2)
  const light = Math.max(L1, L2)
  const dark = Math.min(L1, L2)
  return (light + 0.05) / (dark + 0.05)
}

const rgbaExtractHex = (color: string) => {
  // 只支持 hex(#rrggbb) 直接返回；若 rgba 则忽略 alpha 并合成背景为黑假设
  if (color.startsWith('#') && color.length === 7) return color
  // 简化：返回黑或白占位
  return '#000000'
}

const pickAccessibleColor = (c1: string, c2: string, bg: string, minRatio = 4.5) => {
  const hexBg = rgbaExtractHex(bg)
  const hex1 = rgbaExtractHex(
    c1 === 'rgba(255,255,255,0.88)' ? '#ffffff' : c1.includes('255,255,255') ? '#ffffff' : '#000000'
  )
  const hex2 = rgbaExtractHex(
    c2 === 'rgba(255,255,255,0.88)' ? '#ffffff' : c2.includes('255,255,255') ? '#ffffff' : '#000000'
  )
  const r1 = contrastRatio(hex1, hexBg)
  const r2 = contrastRatio(hex2, hexBg)
  // 优先满足 >= minRatio；都满足取更高；否则取更高
  if (r1 >= minRatio && r2 >= minRatio) return r1 >= r2 ? c1 : c2
  if (r1 >= minRatio) return c1
  if (r2 >= minRatio) return c2
  return r1 >= r2 ? c1 : c2
}

// 改进侧栏背景：如果深色模式，降低亮度并略增饱和；浅色模式提高亮度轻度染色
const deriveSiderBg = (primary: string, base: string, dark: boolean) => {
  const mixRatio = dark ? 0.22 : 0.18
  const mixed = blendColors(base, primary, mixRatio)
  return dark ? hslDarken(mixed, 8) : hslLighten(mixed, 6)
}

const deriveSiderBorder = (siderBg: string, primary: string, dark: boolean) => {
  return dark ? blendColors(siderBg, primary, 0.3) : blendColors('#d9d9d9', primary, 0.25)
}

// 监听系统主题变化
const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
mediaQuery.addEventListener('change', () => {
  if (themeMode.value === 'system') {
    updateTheme()
  }
})

// 监听主题模式和颜色变化
watch(themeMode, updateTheme, { immediate: true })
watch(themeColor, () => {
  updateTheme()
})

// Ant Design 主题配置
const antdTheme = computed(() => ({
  algorithm: isDark.value ? theme.darkAlgorithm : theme.defaultAlgorithm,
  token: {
    colorPrimary: themeColors[themeColor.value],
  },
}))

export function useTheme() {
  const setThemeMode = (mode: ThemeMode) => {
    themeMode.value = mode
    localStorage.setItem('theme-mode', mode)
  }

  const setThemeColor = (color: ThemeColor) => {
    themeColor.value = color
    localStorage.setItem('theme-color', color)
  }

  // 初始化时从localStorage读取设置
  const initTheme = () => {
    const savedMode = localStorage.getItem('theme-mode') as ThemeMode
    const savedColor = localStorage.getItem('theme-color') as ThemeColor

    if (savedMode) {
      themeMode.value = savedMode
    }
    if (savedColor) {
      themeColor.value = savedColor
    }

    updateTheme()
  }

  return {
    themeMode: computed(() => themeMode.value),
    themeColor: computed(() => themeColor.value),
    isDark: computed(() => isDark.value),
    antdTheme,
    themeColors,
    setThemeMode,
    setThemeColor,
    initTheme,
  }
}
