<template>
  <div
    ref="hostWrapperRef"
    class="plugin-page-host"
    :style="hostStyle"
    :data-page-id="page.id"
    :data-plugin-id="page.frontend_plugin || ''"
    :data-theme="themeIsDark ? 'dark' : 'light'"
  >
    <iframe
      v-if="frameSrc && !loadError"
      :key="loadGeneration"
      ref="frameRef"
      class="plugin-page-frame"
      :src="frameSrc"
      :title="page.title"
      :data-load-generation="loadGeneration"
      sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads allow-same-origin"
      @load="handleFrameLoad"
      @error="handleFrameError"
    />
    <a-result
      v-else-if="loadError"
      status="warning"
      title="插件页面加载失败"
      :sub-title="loadError"
    >
      <template #extra>
        <a-button type="primary" @click="retryLoad">
          <template #icon>
            <ReloadOutlined />
          </template>
          重试
        </a-button>
      </template>
    </a-result>
    <a-result
      v-else
      status="warning"
      title="插件页面缺少入口"
      sub-title="该页面声明未提供可加载的 iframe url。"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ReloadOutlined } from '@ant-design/icons-vue'

import { OpenAPI } from '@/api'
import type { PageDeclaration } from '@/router/pageDeclarations'
import { useAppBackground } from '@/composables/useAppBackground'
import { useTheme, type ThemeColor } from '@/composables/useTheme'

const props = defineProps<{
  page: PageDeclaration
}>()

const logger = window.electronAPI.getLogger('插件页面宿主')

const { cssVars: backgroundCssVars } = useAppBackground()
const { isDark: themeIsDark, themeColor, uiScale } = useTheme()

const hostWrapperRef = ref<HTMLElement | null>(null)
const frameRef = ref<HTMLIFrameElement | null>(null)

const loadError = ref('')
const loadGeneration = ref(1)
const retryNonce = ref(0)
let loadTimeoutId: number | null = null
const LOAD_TIMEOUT_MS = 8000

const backendBase = computed(() => {
  return (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
})

function appendRetryNonce(url: string, nonce: number): string {
  if (nonce === 0) {
    return url
  }

  const fragmentIndex = url.indexOf('#')
  const resourceUrl = fragmentIndex >= 0 ? url.slice(0, fragmentIndex) : url
  const fragment = fragmentIndex >= 0 ? url.slice(fragmentIndex) : ''
  const separator = resourceUrl.includes('?') ? '&' : '?'
  return `${resourceUrl}${separator}automas_retry=${nonce}${fragment}`
}

const frameSrc = computed(() => {
  const rawUrl = props.page.url?.trim()
  if (!rawUrl) {
    return ''
  }
  const baseUrl =
    /^https?:\/\//i.test(rawUrl) || rawUrl.startsWith('//')
      ? rawUrl
      : rawUrl.startsWith('/')
        ? `${backendBase.value}${rawUrl}`
        : `${backendBase.value}/${rawUrl.replace(/^\/+/, '')}`
  return appendRetryNonce(baseUrl, retryNonce.value)
})

const hostStyle = computed(() => ({
  ...backgroundCssVars.value,
  '--v6-color-is-dark': themeIsDark.value ? '1' : '0',
  '--v6-color-theme-name': themeColor.value,
  '--v6-ui-scale-host': String(uiScale.value),
}))

const postThemeMessage = () => {
  const frame = frameRef.value
  if (!frame?.contentWindow) return
  // 受 sandbox 限制，postMessage 必须使用 '*' targetOrigin；
  // 仅传递非敏感主题 token，不包含认证信息。
  const payload = {
    type: 'automas-theme-update',
    isDark: themeIsDark.value,
    primaryColor: themeColor.value as ThemeColor,
    uiScale: uiScale.value,
  }
  try {
    frame.contentWindow.postMessage(payload, '*')
  } catch (error) {
    logger.warn(`向插件页面推送主题失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

const clearLoadTimeout = () => {
  if (loadTimeoutId !== null) {
    window.clearTimeout(loadTimeoutId)
    loadTimeoutId = null
  }
}

const armLoadTimeout = () => {
  clearLoadTimeout()
  const generation = loadGeneration.value
  loadTimeoutId = window.setTimeout(() => {
    if (generation !== loadGeneration.value) return
    if (!frameRef.value) return
    // 仍在加载未触发 load 事件：判定为超时失败。
    loadError.value = '插件页面加载超时（8s 未触发 load 事件）。请检查插件服务是否可用。'
  }, LOAD_TIMEOUT_MS)
}

const isCurrentFrameEvent = (event: Event): boolean => {
  const frame = event.currentTarget as HTMLIFrameElement | null
  return (
    frame !== null &&
    frame === frameRef.value &&
    frame.getAttribute('data-load-generation') === String(loadGeneration.value)
  )
}

const handleFrameLoad = (event: Event) => {
  if (!isCurrentFrameEvent(event)) return
  clearLoadTimeout()
  loadError.value = ''
  postThemeMessage()
}

const handleFrameError = (event: Event) => {
  if (!isCurrentFrameEvent(event)) return
  clearLoadTimeout()
  loadError.value = '插件 iframe 加载失败（onerror 触发）。请确认插件 url 可访问。'
}

const retryLoad = () => {
  retryNonce.value += 1
  loadError.value = ''
}

const handleThemeMessage = (event: MessageEvent) => {
  // 监听插件页面主动请求当前主题的回询（best-effort，不破坏 sandbox）
  if (!event.source || event.source !== frameRef.value?.contentWindow) return
  const data = event.data as { type?: string } | undefined
  if (data?.type === 'automas-theme-request') {
    postThemeMessage()
  }
}

watch(
  () => [themeIsDark.value, themeColor.value, uiScale.value] as const,
  () => {
    postThemeMessage()
  }
)

watch(
  frameSrc,
  () => {
    loadGeneration.value += 1
    clearLoadTimeout()
    loadError.value = ''
    if (frameSrc.value) {
      armLoadTimeout()
    }
  },
  { immediate: false }
)

onMounted(() => {
  if (frameSrc.value) {
    armLoadTimeout()
  }
  window.addEventListener('message', handleThemeMessage)
})

onBeforeUnmount(() => {
  loadGeneration.value += 1
  clearLoadTimeout()
  window.removeEventListener('message', handleThemeMessage)
})
</script>

<style scoped>
/* host 容器不强制单一布局，由插件页面决定其内部布局；仅提供尺寸与背景兜底。 */
.plugin-page-host {
  display: block;
  width: 100%;
  min-height: calc(100vh - 80px);
  background: var(--app-background-image, none);
  background-color: var(--v6-color-window);
  color: var(--v6-color-text);
  font-family: var(--v6-font-sans);
  /* legacy-mode 兜底：旧插件不消费 v6 token 时仍提供可读基础样式 */
  --automas-legacy-bg: var(--v6-color-surface);
  --automas-legacy-text: var(--v6-color-text);
  --automas-legacy-border: var(--v6-color-border);
}

.plugin-page-frame {
  display: block;
  width: 100%;
  height: 100%;
  min-height: calc(100vh - 80px);
  border: 0;
  border-radius: var(--v6-radius-card);
  background: var(--ant-color-bg-container, var(--v6-color-surface));
}
</style>
