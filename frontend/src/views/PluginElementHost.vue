<template>
  <PluginErrorBoundary
    :extension-id="page.frontend_plugin || page.id"
    :plugin-name="page.title"
    @disable="handleDisableExtension"
    @retry="retryLoad"
  >
    <div
      class="plugin-page plugin-element-host"
      :style="hostStyle"
      :data-theme="themeIsDark ? 'dark' : 'light'"
    >
      <a-spin v-if="loading" size="large" tip="正在加载插件页面" />
      <a-result
        v-else-if="errorMessage"
        class="plugin-host-state"
        status="warning"
        title="插件页面加载失败"
        :sub-title="errorMessage"
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
      <component
        :is="resolvedTag"
        v-else-if="resolvedTag"
        :title="page.title"
        :data-page-id="page.id"
        :data-plugin-id="page.frontend_plugin || ''"
        :data-theme="themeIsDark ? 'dark' : 'light'"
        class="plugin-element-host__root"
      />
      <a-result
        v-else
        class="plugin-host-state"
        status="warning"
        title="插件页面缺少入口"
        sub-title="页面声明未提供可用的 custom element。"
      />
    </div>
  </PluginErrorBoundary>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ReloadOutlined } from '@ant-design/icons-vue'

import type { PageDeclaration } from '@/router/pageDeclarations'
import {
  ensurePluginFrontendPage,
  type PluginFrontendPageRelease,
} from '@/plugin/pluginFrontendLoader'
import { setPluginPageContext } from '@/plugin/pluginPageContext'
import { useAppBackground } from '@/composables/useAppBackground'
import { useTheme } from '@/composables/useTheme'
import { validatePluginEntryUrl } from '@/plugins/ui/pluginSecurity'
import {
  isManifestVersionSupported,
  getSupportedManifestVersion,
} from '@/plugins/ui/pluginUIManifest'
import PluginErrorBoundary from '@/plugins/ui/PluginErrorBoundary.vue'

const props = defineProps<{
  page: PageDeclaration
}>()

const { cssVars: backgroundCssVars } = useAppBackground()
const { isDark: themeIsDark, themeColor, uiScale } = useTheme()

const loading = ref(true)
const errorMessage = ref('')
let loadGeneration = 0
let releasePage: PluginFrontendPageRelease | null = null
let disposed = false

const resolvedTag = computed(() => props.page.element_tag || '')

// 主题 token + 背景 cssVars 通过 host 元素 style 显式提供：
// - CSS 自定义属性会穿透 shadow DOM 边界，shadow root 内可用 var() 消费；
// - 旧插件不识别这些变量时不报错（CSS var() fallback 机制）；
// - 同时写入 data-theme 属性，便于 :host([data-theme="dark"]) 选择器使用。
const hostStyle = computed(() => ({
  ...backgroundCssVars.value,
  '--v6-color-is-dark': themeIsDark.value ? '1' : '0',
  '--v6-color-theme-name': themeColor.value,
  '--v6-ui-scale-host': String(uiScale.value),
  // 显式重申 v6 基础 token，确保 shadow root 内 :host{...} 始终可读到稳定值
  '--v6-color-surface-host': 'var(--v6-color-surface)',
  '--v6-color-text-host': 'var(--v6-color-text)',
  '--v6-color-border-host': 'var(--v6-color-border)',
}))

function syncPageContext(): void {
  setPluginPageContext({
    pageId: props.page.id,
    path: props.page.path,
    title: props.page.title,
    renderer: props.page.renderer,
    source: props.page.source,
    pluginId: props.page.frontend_plugin,
    elementTag: props.page.element_tag,
  })
}

async function loadPage(): Promise<void> {
  const generation = ++loadGeneration
  releasePage?.()
  releasePage = null
  loading.value = true
  errorMessage.value = ''
  syncPageContext()

  // 安全校验：manifest 版本必须受支持
  if (props.page.manifest_version != null) {
    if (!isManifestVersionSupported(props.page.manifest_version)) {
      loading.value = false
      errorMessage.value = `不支持插件 manifest 版本: ${props.page.manifest_version}，当前仅支持版本 ${getSupportedManifestVersion()}`
      return
    }
  }

  // 安全校验：插件入口脚本 URL 必须通过安全审核
  const entryUrl = props.page.entry_asset_url
  if (entryUrl) {
    const validation = validatePluginEntryUrl(entryUrl)
    if (!validation.safe) {
      loading.value = false
      errorMessage.value = `插件入口 URL 安全校验失败: ${validation.reason}`
      return
    }
  }

  try {
    const loadedPageRelease = await ensurePluginFrontendPage(props.page)
    if (disposed || generation !== loadGeneration) {
      loadedPageRelease()
      return
    }
    releasePage = loadedPageRelease
  } catch (error) {
    if (disposed || generation !== loadGeneration) {
      return
    }
    // 失败隔离：custom element 注册/加载失败显示降级提示而非白屏。
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    if (!disposed && generation === loadGeneration) {
      loading.value = false
    }
  }
}

function retryLoad(): void {
  void loadPage()
}

function handleDisableExtension(extensionId?: string): void {
  const logger = window.electronAPI?.getLogger?.('插件Element宿主')
  logger?.warn(`插件扩展已在当前页面停用: extensionId=${extensionId || props.page.id}`)
  loadGeneration += 1
  releasePage?.()
  releasePage = null
  errorMessage.value = `插件扩展 "${extensionId || props.page.id}" 已在当前页面停用；点击重试或重新进入页面即可恢复。`
  loading.value = false
}

watch(
  () => props.page,
  () => {
    void loadPage()
  },
  { deep: true }
)

// 主题变化时不重新加载插件资源，仅依靠 CSS 变量响应式更新（无需副作用）。
watch(
  () => [themeIsDark.value, themeColor.value, uiScale.value] as const,
  () => {
    // 主题 token 通过 hostStyle 自动响应式更新；此处仅作为 observability hook。
  }
)

onMounted(() => {
  void loadPage()
})

onBeforeUnmount(() => {
  disposed = true
  loadGeneration += 1
  releasePage?.()
  releasePage = null
  // 卸载清理：移除页面上下文，避免下一页误读上一页上下文。
  setPluginPageContext(null)
})
</script>

<style scoped>
/* host 容器不强制单一布局，由 custom element 决定其内部布局；仅提供尺寸与背景兜底。 */
.plugin-element-host {
  display: flex;
  align-items: stretch;
  justify-content: center;
  min-height: 100%;
  background: var(--app-background-image, none);
  background-color: var(--v6-color-window);
  color: var(--v6-color-text);
  font-family: var(--v6-font-sans);
}

.plugin-element-host__root {
  display: block;
  width: 100%;
  min-height: 100%;
  /* legacy-mode 兜底：旧插件未应用自身样式时，仍提供可读的默认外观 */
  color: var(--v6-color-text);
  background: var(--v6-color-surface);
  font-family: var(--v6-font-sans);
  font-size: 14px;
  line-height: 1.5;
}

.plugin-host-state {
  align-self: flex-start;
  width: min(560px, calc(100% - var(--v6-space-8)));
  margin: var(--v6-space-8) auto 0;
  padding: var(--v6-space-5);
  border: 1px solid var(--v6-color-border);
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-surface) 78%, transparent);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.plugin-host-state :deep(.ant-result-icon) {
  display: none;
}

.plugin-host-state :deep(.ant-result-title) {
  font-size: var(--v6-font-size-lg);
}

.plugin-host-state :deep(.ant-result-subtitle) {
  font-size: var(--v6-font-size-sm);
}
</style>
