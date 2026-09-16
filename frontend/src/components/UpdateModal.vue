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
      <!-- 更新内容展示：按版本分区块，破坏性变更 / 本次亮点置顶 -->
      <div class="update-content">
        <ChangelogView :data="updateData" :empty-text="t('comp.changelog.loadFailed')" />
      </div>

      <!-- 操作按钮 -->
      <div class="update-footer">
        <div class="update-actions">
          <a-button @click="handleCancel">{{ t('comp.notNow') }}</a-button>
          <a-button type="primary" @click="handleDownload">{{ t('comp.downloadUpdate') }}</a-button>
        </div>
      </div>
    </div>
  </a-modal>

  <!-- 独立的下载窗口 -->
  <UpdateDownloadModal />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import ChangelogView from './ChangelogView.vue'
import UpdateDownloadModal from './UpdateDownloadModal.vue'
import { useUpdateDownload } from '@/composables/useUpdateDownload'
import type { ChangelogData } from '@/utils/changelog'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('更新模态框')

// Props 定义
interface Props {
  visible: boolean
  /** 版本号 -> 分类 -> 条目，来自 /api/update/check 的 update_info */
  updateData: ChangelogData
  latestVersion?: string
}

const props = defineProps<Props>()

// Emits 定义
const emit = defineEmits<{
  confirmed: []
  'update:visible': [value: boolean]
}>()

const { start } = useUpdateDownload()

// 计算最新版本号
const latestVersion = computed(() => {
  return props.latestVersion || ''
})

// 计算属性 - 响应式地接收外部 visible 状态
const visible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const updateData = computed(() => props.updateData)

// 处理下载按钮点击
const handleDownload = async () => {
  logger.info('点击下载按钮')
  visible.value = false
  await start(props.latestVersion || '', props.updateData)
}

// 关闭弹窗
const handleCancel = () => {
  visible.value = false
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
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
  /* 拇指颜色 / 轨道颜色 */
}

/* WebKit（Chrome/Edge）：细、半透明、悬停时稍亮 */
:deep(.update-content::-webkit-scrollbar) {
  width: 8px;
  /* 滚动条更细 */
}

:deep(.update-content::-webkit-scrollbar-track) {
  background: transparent;
  /* 轨道透明，不显眼 */
}

:deep(.update-content::-webkit-scrollbar-thumb) {
  background: rgba(255, 255, 255, 0.12);
  /* 深色模式下更淡 */
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: padding-box;
  /* 让边缘更柔和 */
}

/* 悬停时略微提升对比度，便于发现 */
:deep(.update-content:hover::-webkit-scrollbar-thumb) {
  background: rgba(255, 255, 255, 0.22);
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
