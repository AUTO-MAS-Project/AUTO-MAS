<template>
  <a-modal
    v-model:open="visible"
    title="系统公告"
    :width="800"
    :footer="null"
    :closable="false"
    :mask-closable="false"
    class="notice-modal"
  >
    <div v-if="notices.length > 0" class="notice-container">
      <!-- 公告标签页 - 竖直布局 -->
      <a-tabs
        v-model:activeKey="activeNoticeKey"
        tab-position="left"
        class="notice-tabs"
        :tabBarStyle="{ width: '200px' }"
      >
        <a-tab-pane
          v-for="(content, title) in noticeData"
          :key="title"
          :tab="title"
          class="notice-tab-pane"
        >
          <div class="notice-content">
            <div class="markdown-content" v-html="renderMarkdown(content)"></div>
          </div>
        </a-tab-pane>
      </a-tabs>

      <!-- 底部操作按钮 -->
      <div class="notice-footer">
        <div class="notice-pagination">
          <span class="pagination-text"> 共 {{ notices.length }} 个公告 </span>
        </div>

        <div class="notice-actions">
          <a-button
            type="primary"
            @click="confirmNotices"
            :loading="confirming"
            class="confirm-button"
          >
            我知道了
          </a-button>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import MarkdownIt from 'markdown-it'
import { Service } from '@/api/services/Service'

interface Props {
  visible: boolean
  noticeData: Record<string, string>
}

interface Emits {
  (e: 'update:visible', visible: boolean): void
  (e: 'confirmed'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value),
})

const confirming = ref(false)
const activeNoticeKey = ref('')

// 初始化 markdown 解析器
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
})

// 获取公告标题列表
const notices = computed(() => Object.keys(props.noticeData))

// 当前公告索引
const currentNoticeIndex = computed(() => {
  return notices.value.findIndex(title => title === activeNoticeKey.value)
})

// 渲染 markdown
const renderMarkdown = (content: string) => {
  return md.render(content)
}

// 确认所有公告
const confirmNotices = async () => {
  confirming.value = true
  try {
    const response = await Service.confirmNoticeApiInfoNoticeConfirmPost()
    if (response.code === 200) {
      // message.success('公告已确认')
      visible.value = false
      emit('confirmed')
    } else {
      message.error(response.message || '确认公告失败')
    }
  } catch (error) {
    console.error('确认公告失败:', error)
    message.error('确认公告失败，请重试')
  } finally {
    confirming.value = false
  }
}

// 监听公告数据变化，设置默认选中第一个公告
watch(
  () => props.noticeData,
  newData => {
    const titles = Object.keys(newData)
    if (titles.length > 0 && !activeNoticeKey.value) {
      activeNoticeKey.value = titles[0]
    }
  },
  { immediate: true }
)

// 监听弹窗显示状态，重置到第一个公告
watch(visible, newVisible => {
  if (newVisible && notices.value.length > 0) {
    activeNoticeKey.value = notices.value[0]
  }
})
</script>

<style scoped>
.notice-modal :deep(.ant-modal-body) {
  padding: 16px 24px;
  max-height: 70vh;
  overflow: hidden;
}

.notice-container {
  display: flex;
  flex-direction: column;
  height: 60vh;
}

.notice-tabs {
  flex: 1;
  min-height: 0;
}

.notice-tabs :deep(.ant-tabs-tab-list) {
  width: 200px;
}

.notice-tabs :deep(.ant-tabs-tab) {
  text-align: left;
  padding: 8px 16px;
}

.notice-tabs :deep(.ant-tabs-content-holder) {
  max-height: 50vh;
  overflow-y: auto;
  padding-left: 16px;
  /* 隐藏滚动条但保持滚动功能 */
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE 和 Edge */
}

/* 隐藏 WebKit 浏览器的滚动条 */
.notice-tabs :deep(.ant-tabs-content-holder)::-webkit-scrollbar {
  display: none;
}

.notice-tab-pane {
  height: 100%;
}

.notice-content {
  padding: 0;
}

.markdown-content {
  line-height: 1.6;
  color: var(--ant-color-text);
}

.markdown-content :deep(h1) {
  font-size: 24px;
  font-weight: 600;
  margin: 16px 0 12px 0;
  color: var(--ant-color-text);
  border-bottom: 2px solid var(--ant-color-border);
  padding-bottom: 8px;
}

.markdown-content :deep(h2) {
  font-size: 20px;
  font-weight: 600;
  margin: 16px 0 10px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0 8px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(p) {
  margin: 8px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-content :deep(li) {
  margin: 4px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(strong) {
  font-weight: 600;
  color: var(--ant-color-text);
}

.markdown-content :deep(code) {
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 1em;
  color: var(--ant-color-primary);
  border: 1px solid var(--ant-color-border-secondary);
  font-weight: 600;
  letter-spacing: 0.5px;
}

.markdown-content :deep(pre) {
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-content :deep(pre code) {
  background: none;
  padding: 0;
  border-radius: 0;
}

.markdown-content :deep(a) {
  color: var(--ant-color-primary);
  text-decoration: none;
}

.markdown-content :deep(a:hover) {
  text-decoration: underline;
}

.markdown-content :deep(blockquote) {
  border-left: 4px solid var(--ant-color-primary);
  margin: 12px 0;
  padding: 8px 16px;
  color: var(--ant-color-text-secondary);
}

.notice-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border);
}

.notice-pagination {
  flex: 1;
}

.pagination-text {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.notice-actions {
  display: flex;
  gap: 8px;
}

.confirm-button {
  min-width: 100px;
  height: 36px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .notice-modal :deep(.ant-modal) {
    width: 95vw !important;
    margin: 10px;
  }

  .notice-modal :deep(.ant-modal-body) {
    padding: 12px 16px;
    max-height: 60vh;
  }

  .notice-container {
    height: 50vh;
  }

  .notice-tabs :deep(.ant-tabs-tab-list) {
    width: 120px;
  }

  .notice-tabs :deep(.ant-tabs-content-holder) {
    max-height: 40vh;
    padding-left: 8px;
  }

  .notice-footer {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .notice-actions {
    justify-content: center;
  }
}
</style>
