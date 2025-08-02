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
}

// 监听系统主题变化
const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
mediaQuery.addEventListener('change', () => {
  if (themeMode.value === 'system') {
    updateTheme()
  }
})

// 监听主题模式变化
watch(themeMode, updateTheme, { immediate: true })

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
