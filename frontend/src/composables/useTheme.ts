import { ref, computed, watch } from 'vue'
import { theme } from 'ant-design-vue'

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

  // 更新CSS变量
  updateCSSVariables()
}

// 更新CSS变量
const updateCSSVariables = () => {
  const root = document.documentElement
  const primaryColor = themeColors[themeColor.value]
  
  if (isDark.value) {
    // 深色模式变量
    root.style.setProperty('--ant-color-primary', primaryColor)
    root.style.setProperty('--ant-color-primary-hover', lightenColor(primaryColor, 10))
    root.style.setProperty('--ant-color-primary-bg', `${primaryColor}1a`)
    root.style.setProperty('--ant-color-text', 'rgba(255, 255, 255, 0.88)')
    root.style.setProperty('--ant-color-text-secondary', 'rgba(255, 255, 255, 0.65)')
    root.style.setProperty('--ant-color-text-tertiary', 'rgba(255, 255, 255, 0.45)')
    root.style.setProperty('--ant-color-bg-container', '#141414')
    root.style.setProperty('--ant-color-bg-layout', '#000000')
    root.style.setProperty('--ant-color-bg-elevated', '#1f1f1f')
    root.style.setProperty('--ant-color-border', '#424242')
    root.style.setProperty('--ant-color-border-secondary', '#303030')
    root.style.setProperty('--ant-color-error', '#ff4d4f')
    root.style.setProperty('--ant-color-success', '#52c41a')
    root.style.setProperty('--ant-color-warning', '#faad14')
  } else {
    // 浅色模式变量
    root.style.setProperty('--ant-color-primary', primaryColor)
    root.style.setProperty('--ant-color-primary-hover', darkenColor(primaryColor, 10))
    root.style.setProperty('--ant-color-primary-bg', `${primaryColor}1a`)
    root.style.setProperty('--ant-color-text', 'rgba(0, 0, 0, 0.88)')
    root.style.setProperty('--ant-color-text-secondary', 'rgba(0, 0, 0, 0.65)')
    root.style.setProperty('--ant-color-text-tertiary', 'rgba(0, 0, 0, 0.45)')
    root.style.setProperty('--ant-color-bg-container', '#ffffff')
    root.style.setProperty('--ant-color-bg-layout', '#f5f5f5')
    root.style.setProperty('--ant-color-bg-elevated', '#ffffff')
    root.style.setProperty('--ant-color-border', '#d9d9d9')
    root.style.setProperty('--ant-color-border-secondary', '#d9d9d9')
    root.style.setProperty('--ant-color-error', '#ff4d4f')
    root.style.setProperty('--ant-color-success', '#52c41a')
    root.style.setProperty('--ant-color-warning', '#faad14')
  }
}

// 颜色工具函数
const hexToRgb = (hex: string) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : null
}

const rgbToHex = (r: number, g: number, b: number) => {
  return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)
}

const lightenColor = (hex: string, percent: number) => {
  const rgb = hexToRgb(hex)
  if (!rgb) return hex
  
  const { r, g, b } = rgb
  const amount = Math.round(2.55 * percent)
  
  return rgbToHex(
    Math.min(255, r + amount),
    Math.min(255, g + amount),
    Math.min(255, b + amount)
  )
}

const darkenColor = (hex: string, percent: number) => {
  const rgb = hexToRgb(hex)
  if (!rgb) return hex
  
  const { r, g, b } = rgb
  const amount = Math.round(2.55 * percent)
  
  return rgbToHex(
    Math.max(0, r - amount),
    Math.max(0, g - amount),
    Math.max(0, b - amount)
  )
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
watch(themeColor, updateTheme)

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
