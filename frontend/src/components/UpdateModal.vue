<template>
  <a-modal
    v-model:open="visible"
    :title="`发现新版本 ${latestVersion || ''}`"
    :width="800"
    :footer="null"
    :mask-closable="false"
    class="update-modal"
  >

  <div v-if="hasUpdate" class="update-container">
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
          <a-button v-if="!downloading && !downloaded" @click="visible = false">暂不更新</a-button>
          <a-button v-if="!downloading && !downloaded" type="primary" @click="downloadUpdate">
            下载更新
          </a-button>

          <a-button v-if="downloading" type="primary" :loading="true" disabled>
            下载中...（后端进度）
          </a-button>

          <a-button v-if="downloaded" type="primary" :loading="installing" @click="installUpdate">
            {{ installing ? '正在安装...' : '立即安装' }}
          </a-button>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import MarkdownIt from 'markdown-it'
import { Service } from '@/api/services/Service.ts'

const visible = ref(false)
const hasUpdate = ref(false)
const downloading = ref(false)
const downloaded = ref(false)
const installing = ref(false)
const updateContent = ref("")
const latestVersion = ref("")

// markdown 渲染器
const md = new MarkdownIt({ html: true, linkify: true, typographer: true })
const renderMarkdown = (content: string) => md.render(content)

/** 将接口的 update_info 对象转成 Markdown 文本 */
function updateInfoToMarkdown(
  info: unknown,
  version?: string,
  header = '更新内容'
): string {
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
  const keys = Array.from(
    new Set([...preferredOrder, ...Object.keys(obj)])
  )

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

// 初始化弹窗流程
const initUpdateCheck = async () => {
  try {
    const version = import.meta.env.VITE_APP_VERSION || '0.0.0'
    const response = await Service.checkUpdateApiUpdateCheckPost({ current_version: version })

    if (response.code === 200 && response.if_need_update) {
      hasUpdate.value = true
      latestVersion.value = response.latest_version || ''
      // ✅ 核心修改：把对象转成 Markdown 再给渲染器
      updateContent.value = updateInfoToMarkdown(
        response.update_info,
        response.latest_version,
        '更新内容'
      )
      visible.value = true
    }
  } catch (err) {
    console.error('检查更新失败:', err)
  }
}

// 下载更新
const downloadUpdate = async () => {
  downloading.value = true
  try {
    const res = await Service.downloadUpdateApiUpdateDownloadPost()
    if (res.code === 200) {
      downloaded.value = true
    } else {
      message.error(res.message || '下载失败')
    }
  } catch (err) {
    console.error('下载更新失败:', err)
    message.error('下载更新失败')
  } finally {
    downloading.value = false
  }
}

// 安装更新
const installUpdate = async () => {
  installing.value = true
  try {
    const res = await Service.installUpdateApiUpdateInstallPost()
    if (res.code === 200) {
      message.success('安装启动')
      visible.value = false
    } else {
      message.error(res.message || '安装失败')
    }
  } catch (err) {
    console.error('安装失败:', err)
    message.error('安装失败')
  } finally {
    installing.value = false
  }
}

onMounted(() => {
  initUpdateCheck()
})

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
  scrollbar-color: rgba(255,255,255,0.14) transparent; /* 拇指颜色 / 轨道颜色 */
}

/* WebKit（Chrome/Edge）：细、半透明、悬停时稍亮 */
:deep(.update-content::-webkit-scrollbar) {
  width: 8px;                /* 滚动条更细 */
}

:deep(.update-content::-webkit-scrollbar-track) {
  background: transparent;   /* 轨道透明，不显眼 */
}

:deep(.update-content::-webkit-scrollbar-thumb) {
  background: rgba(255,255,255,0.12); /* 深色模式下更淡 */
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: padding-box;      /* 让边缘更柔和 */
}

/* 悬停时略微提升对比度，便于发现 */
:deep(.update-content:hover::-webkit-scrollbar-thumb) {
  background: rgba(255,255,255,0.22);
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
