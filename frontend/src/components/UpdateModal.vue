<template>
  <a-modal
    v-model:open="visible"
    :title="`发现新版本 ${latestVersion || ''}`"
    :width="800"
    :footer="null"
    :mask-closable="false"
    :z-index="9999"
    class="update-modal"
  >
    <div class="update-container">
      <!-- 更新内容展示 -->
      <div class="update-content">
        <div
          ref="markdownContentRef"
          class="markdown-content"
          v-html="renderMarkdown(updateContent)"
        ></div>
      </div>

      <!-- 操作按钮 -->
      <div class="update-footer">
        <div class="update-actions">
          <a-button @click="handleCancel">暂不更新</a-button>
          <a-button type="primary" @click="handleDownload"> 下载更新 </a-button>
        </div>
      </div>
    </div>
  </a-modal>

  <!-- 独立的下载窗口 -->
  <UpdateDownloadModal
    v-model:visible="showDownloadModal"
    :latest-version="latestVersion"
    :update-data="updateData"
    @completed="handleDownloadCompleted"
    @cancelled="handleDownloadCancelled"
    @install-requested="handleInstallRequested"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import UpdateDownloadModal from './UpdateDownloadModal.vue'

// Props 定义
interface Props {
  visible: boolean
  updateData: Record<string, string[]>
  latestVersion?: string
}

const props = defineProps<Props>()

// Emits 定义
const emit = defineEmits<{
  confirmed: []
  'update:visible': [value: boolean]
}>()

// 内部状态
const hasUpdate = ref(false)
const showDownloadModal = ref(false)

// 计算最新版本号
const latestVersion = computed(() => {
  return props.latestVersion || ''
})

// 计算属性 - 响应式地接收外部 visible 状态
const visible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

// 计算属性 - 转换 updateData 为 markdown
const updateContent = computed(() => {
  return updateInfoToMarkdown(props.updateData, latestVersion.value, '更新内容')
})

// markdown 渲染器
const md = new MarkdownIt({ html: true, linkify: true, typographer: true })
const renderMarkdown = (content: string) => md.render(content)

/** 将接口的 update_info 对象转成 Markdown 文本 */
function updateInfoToMarkdown(info: unknown, version?: string, header = '更新内容'): string {
  // 如果后端直接给了字符串，直接返回
  if (typeof info === 'string') return info

  if (!info || typeof info !== 'object') return ''

  const obj = info as Record<string, unknown>
  const lines: string[] = []

  // 顶部标题
  if (version) {
    lines.push(`### ${version} ${header}`)
  } else {
    lines.push(`### ${header}`)
  }
  lines.push('') // 空行

  // 希望按这个顺序展示；其余未知键追加在后
  const preferredOrder = ['修复BUG', '程序优化', '新增功能']
  const keys = Array.from(new Set([...preferredOrder, ...Object.keys(obj)]))

  for (const key of keys) {
    const val = obj[key]
    if (Array.isArray(val) && val.length > 0) {
      lines.push(`#### ${key}`)
      for (const item of val) {
        // 防御：数组里既可能是字符串也可能是对象
        if (typeof item === 'string') {
          lines.push(`- ${item}`)
        } else {
          // 兜底：把对象友好地 stringify（去掉引号）
          lines.push(`- ${JSON.stringify(item, null, 0)}`)
        }
      }
      lines.push('') // 每段之间空一行
    }
  }

  return lines.join('\n')
}

// 初始化检查
if (props.updateData && Object.keys(props.updateData).length > 0) {
  hasUpdate.value = true
}

// 处理下载按钮点击
const handleDownload = () => {
  console.log('[UpdateModal] 点击下载按钮')
  console.log('[UpdateModal] 当前props:', {
    updateData: props.updateData,
    latestVersion: props.latestVersion,
    visible: props.visible,
  })
  // 关闭当前窗口，显示下载窗口
  visible.value = false
  showDownloadModal.value = true
  console.log('[UpdateModal] 设置showDownloadModal为true:', showDownloadModal.value)
}

// 关闭弹窗
const handleCancel = () => {
  visible.value = false
  emit('confirmed')
}

// 下载窗口事件处理
const handleDownloadCompleted = () => {
  showDownloadModal.value = false
  emit('confirmed')
}

const handleDownloadCancelled = () => {
  showDownloadModal.value = false
  emit('confirmed')
}

const handleInstallRequested = () => {
  showDownloadModal.value = false
  emit('confirmed')
}
</script>

<style scoped>
.update-modal :deep(.ant-modal-body) {
  padding: 16px 24px;
  max-height: 70vh;
  overflow: hidden;
}

.update-container {
  display: flex;
  flex-direction: column;
  height: 60vh;
}

.update-content {
  flex: 1;
  overflow-y: auto;
  padding-right: 12px;
}
/* Firefox：细滚动条 & 低对比 */
:deep(.update-content) {
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent; /* 拇指颜色 / 轨道颜色 */
}

/* WebKit（Chrome/Edge）：细、半透明、悬停时稍亮 */
:deep(.update-content::-webkit-scrollbar) {
  width: 8px; /* 滚动条更细 */
}

:deep(.update-content::-webkit-scrollbar-track) {
  background: transparent; /* 轨道透明，不显眼 */
}

:deep(.update-content::-webkit-scrollbar-thumb) {
  background: rgba(255, 255, 255, 0.12); /* 深色模式下更淡 */
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: padding-box; /* 让边缘更柔和 */
}

/* 悬停时略微提升对比度，便于发现 */
:deep(.update-content:hover::-webkit-scrollbar-thumb) {
  background: rgba(255, 255, 255, 0.22);
}
.markdown-content {
  line-height: 1.6;
  color: var(--ant-color-text);
}

.update-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  border-top: 1px solid var(--ant-color-border);
  padding-top: 12px;
}

.update-actions {
  display: flex;
  gap: 10px;
}
</style>
