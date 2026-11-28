<template>
  <!-- ══ 配置预览：备份摘要（纯读不恢复）══ -->
  <AppModal
    :open="true"
    @update:open="emit('close')"
    footer="close"
    width="540px"
    :body-style="{ maxHeight: '70vh', overflowY: 'auto' }"
  >
    <template #header>
      <!-- 预览标题区：专项可用 #preview-title 插槽自定义，缺省用「配置预览 · 时间」 -->
      <slot name="preview-title" :time="previewTime">
        {{ `${t('core.edit.configRestorePreviewTitle')} · ${previewTime}` }}
      </slot>
    </template>
    <a-spin :spinning="previewLoading">
      <p v-if="previewError" class="restore-desc">{{ previewError }}</p>
      <a-alert
        v-if="previewWarnings.length"
        class="preview-warning"
        type="warning"
        show-icon
        :message="t('core.edit.configRestoreUnrestorableTitle')"
      >
        <template #description>
          <div>{{ t('core.edit.configRestoreUnrestorableDesc') }}</div>
          <div v-for="warning in previewWarnings" :key="warning">{{ warning }}</div>
        </template>
      </a-alert>
      <!-- 自定义预览：专项通过 #preview 插槽完全接管预览区（字段型适配器等）；
           raw 为后端预览响应原文（内置 info/account/tasks/instances 之外的
           自定义结构从这里取） -->
      <slot
        v-if="!previewError"
        name="preview"
        :data="previewData"
        :raw="previewRaw"
        :target="target.key"
        :format-value="formatValue"
        :field-label="fieldLabel"
      >
        <!-- 用户级：基本信息 + 账号 + 任务编排；载荷无字段语义时不渲染空表，
             但保留「无可展示摘要」提示（与脚本级一致的基座默认兜底） -->
        <template v-if="previewRaw?.sections?.length">
          <section v-for="section in previewRaw.sections" :key="section.name">
            <h4 class="preview-section-title">{{ section.label }}</h4>
            <a-descriptions :column="1" size="small" bordered class="preview-box">
              <a-descriptions-item v-for="row in section.rows" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
          </section>
        </template>
        <template v-else-if="target.kind === 'user'">
          <template v-if="previewRows.length || previewData.tasks.length">
            <h4 class="preview-section-title">{{ t('core.edit.basicInfo') }}</h4>
            <a-descriptions :column="1" size="small" bordered class="preview-box">
              <a-descriptions-item v-for="row in previewRows" :key="row.label" :label="row.label">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
            <h4 class="preview-section-title">{{ t('core.edit.configRestorePreviewTasks') }}</h4>
            <div v-if="previewData.tasks.length" class="preview-task-list">
              <span
                v-for="task in previewData.tasks"
                :key="task.app_id"
                class="preview-task-tag"
                :class="{ active: task.enabled }"
              >
                {{ task.app_name }}
              </span>
            </div>
            <NoData v-else :description="t('core.edit.configRestorePreviewNoTasks')" />
          </template>
          <NoData v-else :description="t('core.edit.configRestorePreviewEmpty')" />
        </template>
        <!-- 脚本级：实例列表可展开查看账号/任务明细 -->
        <template v-else>
          <NoData
            v-if="!previewData.instances.length"
            :description="t('core.edit.configRestorePreviewEmpty')"
          />
          <a-collapse v-else class="preview-instance-list" :bordered="false">
            <a-collapse-panel v-for="inst in previewData.instances" :key="inst.idx">
              <template #header>
                <span class="preview-instance-name">
                  {{ `${String(inst.idx).padStart(2, '0')} - ${inst.name}` }}
                </span>
                <a-tag v-if="inst.active" color="blue">
                  {{ t('core.edit.configRestorePreviewActive') }}
                </a-tag>
              </template>
              <a-descriptions :column="1" size="small" bordered class="preview-box">
                <a-descriptions-item
                  v-for="f in inst.account"
                  :key="f.key"
                  :label="fieldLabel(f.key)"
                >
                  {{ formatValue(f.key, f.value) }}
                </a-descriptions-item>
              </a-descriptions>
              <div v-if="inst.tasks.length" class="preview-task-list">
                <span
                  v-for="task in inst.tasks"
                  :key="task.app_id"
                  class="preview-task-tag"
                  :class="{ active: task.enabled }"
                >
                  {{ task.app_name }}
                </span>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </template>
      </slot>
      <!-- ══ 备份文件（基座统一兜底：预览载荷的标准 files 字段）══
           归档内文件清单恒渲染在预览区最下方（默认收起，标题带数量），
           路径为超链接，点击查看原始内容；专项未提供 files 字段时不渲染，
           未实现 readFile 时点击提示后端原因 -->
      <a-collapse v-if="previewFiles.length" class="preview-files-collapse" :bordered="false">
        <a-collapse-panel>
          <template #header>
            <span class="preview-files-title">
              {{ `${t('core.edit.configRestoreBackupFiles')} (${previewFiles.length})` }}
            </span>
          </template>
          <div class="preview-file-list">
            <button
              v-for="f in previewFiles"
              :key="f.path"
              type="button"
              class="preview-file-link"
              @click="fileItem = f"
            >
              <span class="preview-file-path">{{ f.path }}</span>
              <span class="preview-file-size">{{ formatFileSize(f.size) }}</span>
            </button>
          </div>
        </a-collapse-panel>
      </a-collapse>
      <ConfigRestoreFile
        v-if="fileItem"
        :item="fileItem"
        :target="target.key"
        :time="item.time"
        :read-file="api.readFile"
        @close="fileItem = null"
      />
    </a-spin>
    <template v-if="onDetail" #footer-left>
      <!-- 操作按钮常驻弹窗底部（footer 不随 body 滚动）；「查看详细配置」
           依赖父组件的 onDetail 回调（恢复 + 拉起查看会话），专项未提供时
           不渲染，避免出现无响应的按钮 -->
      <a-tooltip :title="t('core.edit.configRestoreDetailHint', { script: scriptName })">
        <a-button :disabled="disabled || !previewRestoreAllowed" @click="handlePreviewDetail">
          {{ t('core.edit.configRestoreDetailView') }}
        </a-button>
      </a-tooltip>
    </template>
  </AppModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AppModal } from '@/components/ui'
import ConfigRestoreFile from './ConfigRestoreFile.vue'
import {
  backupSummaryRows,
  formatBackupTime,
  formatFileSize,
  type BackupItem,
  type BackupFileItem,
  type ConfigRestoreProps,
} from './configRestore'

const props = defineProps<
  Pick<
    ConfigRestoreProps,
    'api' | 'scriptName' | 'disabled' | 'fieldLabels' | 'formatValue' | 'onDetail'
  > & {
    item: BackupItem
    target: ConfigRestoreProps['targets'][number]
    currentSource: string | null
  }
>()
const emit = defineEmits<{ close: []; allowed: [time: string, allowed: boolean] }>()
const { t } = useI18n()
const previewTime = computed(() => formatBackupTime(props.item.time))
const previewLoading = ref(true)
const previewError = ref('')
type Preview = Awaited<ReturnType<ConfigRestoreProps['api']['preview']>> & {
  sections?: { name: string; label: string; rows: { key: string; value: string }[] }[]
  warnings?: string[]
  restoreAllowed?: boolean
  files?: BackupFileItem[]
}
const previewRaw = ref<Preview | null>(null)
// 专项可把额外摘要放在 data 中；旧接口返回平铺结构。
const previewData = computed(() => ({
  info: previewRaw.value?.info ?? [],
  account: previewRaw.value?.account ?? [],
  tasks: previewRaw.value?.tasks ?? [],
  instances: previewRaw.value?.instances ?? [],
}))
const previewWarnings = computed(() => {
  const warnings = previewRaw.value?.warnings
  return Array.isArray(warnings) ? warnings.filter(w => typeof w === 'string') : []
})
const previewRestoreAllowed = computed(
  () =>
    !!previewRaw.value && previewRaw.value.restoreAllowed !== false && !previewWarnings.value.length
)
const previewFiles = computed(() =>
  (previewRaw.value?.files ?? []).filter(f => typeof f?.path === 'string')
)
const fieldLabel = (key: string): string => props.fieldLabels?.[key] ?? key
const formatValue = (key: string, raw: string): string =>
  props.formatValue?.(key, raw) ?? (raw || '—')

const previewRows = computed(() => backupSummaryRows(previewData.value, formatValue, t))
const fileItem = ref<BackupFileItem | null>(null)

watch(
  () => [props.target.key, props.item.time],
  async ([target, time], _, onCleanup) => {
    let current = true
    onCleanup(() => {
      current = false
    })
    previewLoading.value = true
    previewRaw.value = null
    previewError.value = ''
    try {
      const resp = await props.api.preview(target, time)
      if (!current) return
      if (resp.code !== 200)
        throw new Error(resp.message || t('core.edit.configRestorePreviewFailed'))
      previewRaw.value = (resp.data ?? resp) as Preview
    } catch (error) {
      if (!current) return
      previewError.value =
        error instanceof Error ? error.message : t('core.edit.configRestorePreviewFailed')
    } finally {
      if (current) {
        previewLoading.value = false
        emit('allowed', time, previewRestoreAllowed.value)
      }
    }
  },
  { immediate: true }
)

async function handlePreviewDetail() {
  if (props.disabled || !previewRestoreAllowed.value) return
  if ((await props.onDetail?.(props.target.key, props.item, props.currentSource)) !== false)
    emit('close')
}
</script>

<style scoped>
.restore-desc {
  margin: 0 0 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.preview-warning {
  margin-bottom: 12px;
}
/* 预览弹窗滚动由 body-style 限高承担（基座约定：body 是唯一滚动容器） */

/* 配置预览弹窗：摘要表格与任务标签 */
.preview-box {
  margin-bottom: 4px;
}

.preview-section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.preview-task-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preview-task-tag {
  padding: 2px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.preview-task-tag.active {
  color: var(--ant-color-text);
  border-color: var(--ant-color-primary);
}

/* 脚本级预览：实例折叠列表与弹窗底部操作区 */
.preview-instance-list {
  background: transparent;
}

.preview-instance-name {
  font-weight: 600;
}

/* 备份文件节：默认收起的折叠面板（标题带文件数），路径为超链接样式，整行可点 */
.preview-files-collapse {
  background: transparent;
}

.preview-files-collapse :deep(.ant-collapse-header) {
  padding: 8px 0;
}

.preview-files-title {
  font-size: 14px;
  font-weight: 600;
}

.preview-file-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preview-file-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s;
}

.preview-file-link:hover {
  border-color: var(--ant-color-primary);
}

.preview-file-path {
  color: var(--ant-color-primary);
  word-break: break-all;
}

.preview-file-size {
  flex-shrink: 0;
  color: var(--ant-color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
</style>
