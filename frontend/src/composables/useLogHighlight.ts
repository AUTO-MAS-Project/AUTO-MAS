import { computed, ref } from 'vue'
import { useTheme } from './useTheme'

// 日志高亮颜色配置接口
export interface LogHighlightColors {
  // 时间相关
  timestamp: string
  date: string

  // 日志级别
  error: string
  warning: string
  info: string
  debug: string
  trace: string

  // 结构元素
  module: string
  bracket: string

  // 网络相关
  ip: string
  url: string
  port: string

  // 文件系统
  path: string
  filename: string

  // 数据类型
  number: string
  string: string
  boolean: string
  uuid: string

  // 关键词
  errorKeyword: string
  success: string

  // 特殊内容
  stackTrace: string
  json: string
  variable: string
  operator: string
}

// 字体样式配置接口
export interface LogHighlightStyles {
  timestampBold: boolean
  levelBold: boolean
  keywordBold: boolean
  urlUnderline: boolean
}

// 编辑器配置接口
export interface LogEditorConfig {
  fontSize: number
  lineHeight: number
}

// 默认浅色主题颜色
const defaultLightColors: LogHighlightColors = {
  // 时间相关
  timestamp: '0066cc',
  date: '0066cc',

  // 日志级别
  error: 'ff0000',
  warning: 'ff8800',
  info: '0088cc',
  debug: '888888',
  trace: 'aaaaaa',

  // 结构元素
  module: '8800cc',
  bracket: '666666',

  // 网络相关
  ip: '00aa00',
  url: '0066cc',
  port: '009688',

  // 文件系统
  path: '666666',
  filename: '795548',

  // 数据类型
  number: '0066cc',
  string: 'a31515',
  boolean: '0000ff',
  uuid: '607d8b',

  // 关键词
  errorKeyword: 'cc0000',
  success: '00aa00',

  // 特殊内容
  stackTrace: 'b71c1c',
  json: '6a1b9a',
  variable: 'e65100',
  operator: '666666',
}

// 默认深色主题颜色
const defaultDarkColors: LogHighlightColors = {
  // 时间相关
  timestamp: '4fc3f7',
  date: '4fc3f7',

  // 日志级别
  error: 'f44336',
  warning: 'ff9800',
  info: '2196f3',
  debug: '9e9e9e',
  trace: '757575',

  // 结构元素
  module: 'ce93d8',
  bracket: '9e9e9e',

  // 网络相关
  ip: '4caf50',
  url: '03dac6',
  port: '26a69a',

  // 文件系统
  path: 'bdbdbd',
  filename: 'bcaaa4',

  // 数据类型
  number: '64b5f6',
  string: 'ce9178',
  boolean: '569cd6',
  uuid: '90a4ae',

  // 关键词
  errorKeyword: 'ef5350',
  success: '66bb6a',

  // 特殊内容
  stackTrace: 'ff8a80',
  json: 'b39ddb',
  variable: 'ffb74d',
  operator: '9e9e9e',
}

// 默认字体样式
const defaultStyles: LogHighlightStyles = {
  timestampBold: true,
  levelBold: true,
  keywordBold: false,
  urlUnderline: true,
}

// 默认编辑器配置
const defaultEditorConfig: LogEditorConfig = {
  fontSize: 13,
  lineHeight: 1.5,
}

// 存储键名
const STORAGE_KEY_LIGHT = 'log-highlight-colors-light'
const STORAGE_KEY_DARK = 'log-highlight-colors-dark'
const STORAGE_KEY_STYLES = 'log-highlight-styles'
const STORAGE_KEY_EDITOR = 'log-editor-config'

// 全局状态
const lightColors = ref<LogHighlightColors>({ ...defaultLightColors })
const darkColors = ref<LogHighlightColors>({ ...defaultDarkColors })
const styles = ref<LogHighlightStyles>({ ...defaultStyles })
const editorConfig = ref<LogEditorConfig>({ ...defaultEditorConfig })

// 从 localStorage 加载配置
const loadConfig = () => {
  try {
    const savedLight = localStorage.getItem(STORAGE_KEY_LIGHT)
    const savedDark = localStorage.getItem(STORAGE_KEY_DARK)
    const savedStyles = localStorage.getItem(STORAGE_KEY_STYLES)
    const savedEditor = localStorage.getItem(STORAGE_KEY_EDITOR)

    if (savedLight) {
      lightColors.value = { ...defaultLightColors, ...JSON.parse(savedLight) }
    }
    if (savedDark) {
      darkColors.value = { ...defaultDarkColors, ...JSON.parse(savedDark) }
    }
    if (savedStyles) {
      styles.value = { ...defaultStyles, ...JSON.parse(savedStyles) }
    }
    if (savedEditor) {
      editorConfig.value = { ...defaultEditorConfig, ...JSON.parse(savedEditor) }
    }
  } catch (error) {
    console.error('Failed to load log highlight config:', error)
  }
}

// 保存配置到 localStorage
const saveColors = () => {
  try {
    localStorage.setItem(STORAGE_KEY_LIGHT, JSON.stringify(lightColors.value))
    localStorage.setItem(STORAGE_KEY_DARK, JSON.stringify(darkColors.value))
  } catch (error) {
    console.error('Failed to save log highlight colors:', error)
  }
}

const saveStyles = () => {
  try {
    localStorage.setItem(STORAGE_KEY_STYLES, JSON.stringify(styles.value))
  } catch (error) {
    console.error('Failed to save log highlight styles:', error)
  }
}

const saveEditorConfig = () => {
  try {
    localStorage.setItem(STORAGE_KEY_EDITOR, JSON.stringify(editorConfig.value))
  } catch (error) {
    console.error('Failed to save editor config:', error)
  }
}

// 初始化加载
loadConfig()

export function useLogHighlight() {
  const { isDark } = useTheme()

  // 当前使用的颜色（根据主题）
  const currentColors = computed(() => (isDark.value ? darkColors.value : lightColors.value))

  // 计算当前使用的主题名称
  const editorTheme = computed(() => (isDark.value ? 'log-dark' : 'log-light'))

  // 生成字体样式字符串
  const getFontStyle = (isBold: boolean, isUnderline: boolean = false) => {
    const parts: string[] = []
    if (isBold) parts.push('bold')
    if (isUnderline) parts.push('underline')
    return parts.length > 0 ? parts.join(' ') : undefined
  }

  // 注册日志语言和主题
  const registerLogLanguage = (monaco: any) => {
    if (!monaco) return

    try {
      // 检查语言是否已注册
      const languages = monaco.languages.getLanguages()
      const isRegistered = languages.some((lang: any) => lang.id === 'logfile')

      if (!isRegistered) {
        // 注册日志语言
        monaco.languages.register({ id: 'logfile' })

        // 定义语法高亮规则
        monaco.languages.setMonarchTokensProvider('logfile', {
          tokenizer: {
            root: [
              // UUID
              [
                /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/,
                'uuid',
              ],

              // 时间戳 (各种格式)
              [
                /\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(\.\d{1,6})?([+-]\d{2}:?\d{2}|Z)?/,
                'timestamp',
              ],
              [/\d{2}:\d{2}:\d{2}(\.\d{1,6})?/, 'timestamp'],
              [/\[\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(\.\d{1,6})?\]/, 'timestamp'],

              // 日期
              [/\d{4}[-\/]\d{2}[-\/]\d{2}/, 'date'],

              // 日志级别
              [/\b(ERROR|FATAL|CRITICAL|SEVERE)\b/i, 'log-error'],
              [/\b(WARN|WARNING)\b/i, 'log-warning'],
              [/\b(INFO|INFORMATION|NOTICE)\b/i, 'log-info'],
              [/\b(DEBUG)\b/i, 'log-debug'],
              [/\b(TRACE|VERBOSE|FINE|FINER|FINEST)\b/i, 'log-trace'],

              // 堆栈跟踪
              [/^\s*at\s+[\w.$<>]+\(.*\)/, 'stack-trace'],
              [/^\s*at\s+[\w.$<>]+/, 'stack-trace'],
              [/Caused by:.*/, 'stack-trace'],
              [/^\s+\.\.\.\s+\d+\s+more/, 'stack-trace'],

              // JSON 对象/数组
              [/\{[^{}]*\}/, 'json'],

              // 变量赋值 key=value
              [/\b\w+(?==)/, 'variable'],

              // 括号内的内容 (通常是模块名或线程名)
              [/\[[^\]]+\]/, 'log-module'],
              [/\([^)]+\)/, 'bracket'],

              // URL (在 IP 之前匹配)
              [/https?:\/\/[^\s]+/, 'log-url'],

              // IP:Port
              [/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}\b/, 'port'],

              // IP 地址
              [/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/, 'log-ip'],

              // 端口号 (独立的)
              [/:\d{2,5}\b/, 'port'],

              // 文件路径 (Windows)
              [/[A-Za-z]:[\\\/][\w\\\/.-]+/, 'log-path'],
              // 文件路径 (Unix)
              [/\/[\w\/.-]+\.\w+/, 'log-path'],
              // 文件名
              [/\b[\w-]+\.(log|txt|json|xml|yaml|yml|conf|cfg|ini|properties)\b/i, 'filename'],

              // 字符串 (双引号)
              [/"[^"]*"/, 'string'],
              // 字符串 (单引号)
              [/'[^']*'/, 'string'],

              // 布尔值
              [/\b(true|false|null|nil|none)\b/i, 'boolean'],

              // 数字 (包括小数、负数、科学计数法)
              [/-?\b\d+(\.\d+)?([eE][+-]?\d+)?\b/, 'log-number'],

              // 异常和错误关键词
              [
                /\b(Exception|Error|Failed|Failure|Timeout|Abort|Rejected|Denied|Invalid|Illegal)\b/i,
                'log-error-keyword',
              ],

              // 成功关键词
              [
                /\b(Success|Successful|Complete|Completed|OK|Done|Finished|Passed|Accepted|Approved)\b/i,
                'log-success',
              ],

              // 操作符
              [/[=<>!]+/, 'operator'],
            ],
          },
        })
      }

      const s = styles.value

      // 每次都重新定义主题（以应用最新的颜色配置）
      monaco.editor.defineTheme('log-light', {
        base: 'vs',
        inherit: true,
        rules: [
          {
            token: 'timestamp',
            foreground: lightColors.value.timestamp,
            fontStyle: getFontStyle(s.timestampBold),
          },
          { token: 'date', foreground: lightColors.value.date },
          {
            token: 'log-error',
            foreground: lightColors.value.error,
            fontStyle: getFontStyle(s.levelBold),
          },
          {
            token: 'log-warning',
            foreground: lightColors.value.warning,
            fontStyle: getFontStyle(s.levelBold),
          },
          {
            token: 'log-info',
            foreground: lightColors.value.info,
            fontStyle: getFontStyle(s.levelBold),
          },
          { token: 'log-debug', foreground: lightColors.value.debug },
          { token: 'log-trace', foreground: lightColors.value.trace },
          { token: 'log-module', foreground: lightColors.value.module },
          { token: 'bracket', foreground: lightColors.value.bracket },
          { token: 'log-ip', foreground: lightColors.value.ip },
          {
            token: 'log-url',
            foreground: lightColors.value.url,
            fontStyle: getFontStyle(false, s.urlUnderline),
          },
          { token: 'port', foreground: lightColors.value.port },
          { token: 'log-path', foreground: lightColors.value.path },
          { token: 'filename', foreground: lightColors.value.filename },
          { token: 'log-number', foreground: lightColors.value.number },
          { token: 'string', foreground: lightColors.value.string },
          { token: 'boolean', foreground: lightColors.value.boolean },
          { token: 'uuid', foreground: lightColors.value.uuid },
          {
            token: 'log-error-keyword',
            foreground: lightColors.value.errorKeyword,
            fontStyle: getFontStyle(s.keywordBold),
          },
          {
            token: 'log-success',
            foreground: lightColors.value.success,
            fontStyle: getFontStyle(s.keywordBold),
          },
          { token: 'stack-trace', foreground: lightColors.value.stackTrace },
          { token: 'json', foreground: lightColors.value.json },
          { token: 'variable', foreground: lightColors.value.variable },
          { token: 'operator', foreground: lightColors.value.operator },
        ],
        colors: {},
      })

      monaco.editor.defineTheme('log-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
          {
            token: 'timestamp',
            foreground: darkColors.value.timestamp,
            fontStyle: getFontStyle(s.timestampBold),
          },
          { token: 'date', foreground: darkColors.value.date },
          {
            token: 'log-error',
            foreground: darkColors.value.error,
            fontStyle: getFontStyle(s.levelBold),
          },
          {
            token: 'log-warning',
            foreground: darkColors.value.warning,
            fontStyle: getFontStyle(s.levelBold),
          },
          {
            token: 'log-info',
            foreground: darkColors.value.info,
            fontStyle: getFontStyle(s.levelBold),
          },
          { token: 'log-debug', foreground: darkColors.value.debug },
          { token: 'log-trace', foreground: darkColors.value.trace },
          { token: 'log-module', foreground: darkColors.value.module },
          { token: 'bracket', foreground: darkColors.value.bracket },
          { token: 'log-ip', foreground: darkColors.value.ip },
          {
            token: 'log-url',
            foreground: darkColors.value.url,
            fontStyle: getFontStyle(false, s.urlUnderline),
          },
          { token: 'port', foreground: darkColors.value.port },
          { token: 'log-path', foreground: darkColors.value.path },
          { token: 'filename', foreground: darkColors.value.filename },
          { token: 'log-number', foreground: darkColors.value.number },
          { token: 'string', foreground: darkColors.value.string },
          { token: 'boolean', foreground: darkColors.value.boolean },
          { token: 'uuid', foreground: darkColors.value.uuid },
          {
            token: 'log-error-keyword',
            foreground: darkColors.value.errorKeyword,
            fontStyle: getFontStyle(s.keywordBold),
          },
          {
            token: 'log-success',
            foreground: darkColors.value.success,
            fontStyle: getFontStyle(s.keywordBold),
          },
          { token: 'stack-trace', foreground: darkColors.value.stackTrace },
          { token: 'json', foreground: darkColors.value.json },
          { token: 'variable', foreground: darkColors.value.variable },
          { token: 'operator', foreground: darkColors.value.operator },
        ],
        colors: {},
      })
    } catch (error) {
      console.error('Failed to register log language:', error)
    }
  }

  // 更新浅色主题颜色
  const setLightColors = (colors: Partial<LogHighlightColors>) => {
    lightColors.value = { ...lightColors.value, ...colors }
    saveColors()
  }

  // 更新深色主题颜色
  const setDarkColors = (colors: Partial<LogHighlightColors>) => {
    darkColors.value = { ...darkColors.value, ...colors }
    saveColors()
  }

  // 更新字体样式
  const setStyles = (newStyles: Partial<LogHighlightStyles>) => {
    styles.value = { ...styles.value, ...newStyles }
    saveStyles()
  }

  // 更新编辑器配置
  const setEditorConfig = (config: Partial<LogEditorConfig>) => {
    editorConfig.value = { ...editorConfig.value, ...config }
    saveEditorConfig()
  }

  // 重置为默认颜色
  const resetColors = () => {
    lightColors.value = { ...defaultLightColors }
    darkColors.value = { ...defaultDarkColors }
    saveColors()
  }

  // 重置为默认样式
  const resetStyles = () => {
    styles.value = { ...defaultStyles }
    saveStyles()
  }

  // 重置为默认编辑器配置
  const resetEditorConfig = () => {
    editorConfig.value = { ...defaultEditorConfig }
    saveEditorConfig()
  }

  // 重置全部
  const resetToDefaults = () => {
    resetColors()
    resetStyles()
    resetEditorConfig()
  }

  return {
    // 颜色配置
    lightColors: computed(() => lightColors.value),
    darkColors: computed(() => darkColors.value),
    currentColors,
    defaultLightColors,
    defaultDarkColors,

    // 样式配置
    styles: computed(() => styles.value),
    defaultStyles,

    // 编辑器配置
    editorConfig: computed(() => editorConfig.value),
    defaultEditorConfig,

    // 主题
    editorTheme,

    // 方法
    registerLogLanguage,
    setLightColors,
    setDarkColors,
    setStyles,
    setEditorConfig,
    resetColors,
    resetStyles,
    resetEditorConfig,
    resetToDefaults,
  }
}
