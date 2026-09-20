<template>
  <!-- ══ 配置恢复（历史备份浏览 / 预览 / 查看详细 / 一键恢复；MAS 在前脚本在后）══ -->
  <a-modal
    :open="open"
    :title="t('edit.configRestoreTitle')"
    :footer="null"
    width="520px"
    @update:open="onOpenChange"
  >
    <a-alert
      v-if="disabled"
      class="restore-lock-alert"
      type="warning"
      show-icon
      :message="t('edit.configLocked')"
    />
    <a-segmented
      v-model:value="restoreTarget"
      block
      class="restore-target-switch"
      :options="targetOptions"
    />
    <p class="restore-desc">
      {{
        currentTarget?.kind === 'user'
          ? (userDesc ?? t('edit.configRestoreMasDesc', { script: scriptName }))
          : (scriptDesc ?? t('edit.configRestoreScriptDesc', { script: scriptName }))
      }}
      <!-- 当前配置来源（三态专项才有；用户靠它与备份标签对比是否需要跨来源恢复） -->
      <span v-if="currentSource" class="restore-current-source">
        {{ t('edit.configRestoreCurrentSource', { mode: t(sourceLabelKey(currentSource)) }) }}
      </span>
    </p>
    <a-spin :spinning="backupsLoading">
      <a-empty v-if="!backups.length" :description="t('edit.configRestoreEmpty')" />
      <a-list v-else :data-source="backups" size="small" row-key="time">
        <template #renderItem="{ item }">
          <a-list-item>
            <div class="backup-main">
              <span class="backup-time">{{ formatBackupTime(item.time) }}</span>
              <!-- 备份时点的配置来源标签（脚本级/用户级/直控；旧版备份无标注不显示） -->
              <a-tag v-if="item.mode" :color="modeTag(item.mode).color">
                {{ modeTag(item.mode).label }}
              </a-tag>
            </div>
            <a-space>
              <a-button type="link" size="small" @click="handlePreview(item)">
                {{ t('edit.configRestorePreview') }}
              </a-button>
              <a-button size="small" :disabled="disabled" @click="confirmRestore(item)">
                {{ t('edit.configRestoreAction') }}
              </a-button>
            </a-space>
          </a-list-item>
        </template>
      </a-list>
    </a-spin>
  </a-modal>

  <!-- ══ 配置预览：备份摘要（纯读不恢复）══ -->
  <a-modal
    :open="previewOpen"
    width="540px"
    :body-style="{ maxHeight: '70vh', overflowY: 'auto' }"
    @update:open="previewOpen = $event"
  >
    <template #title>
      <!-- 预览标题区：专项可用 #preview-title 插槽自定义，缺省用「配置预览 · 时间」 -->
      <slot name="preview-title" :time="previewTime">
        {{ `${t('edit.configRestorePreviewTitle')} · ${previewTime}` }}
      </slot>
    </template>
    <a-spin :spinning="previewLoading">
      <p v-if="previewError" class="restore-desc">{{ previewError }}</p>
      <!-- 自定义预览：专项通过 #preview 插槽完全接管预览区（字段型适配器等）；
           raw 为后端预览响应原文（内置 info/account/tasks/instances 之外的
           自定义结构从这里取） -->
      <slot
        v-else
        name="preview"
        :data="previewData"
        :raw="previewRaw"
        :target="restoreTarget"
        :format-value="formatValue"
        :field-label="fieldLabel"
      >
        <!-- 用户级：基本信息 + 账号 + 任务编排；载荷无字段语义时不渲染空表，
             但保留「无可展示摘要」提示（与脚本级一致的基座默认兜底） -->
        <template v-if="currentTarget?.kind === 'user'">
          <template v-if="previewRows.length || previewData.tasks.length">
            <h4 class="preview-section-title">{{ t('edit.basicInfo') }}</h4>
            <a-descriptions :column="1" size="small" bordered class="preview-box">
              <a-descriptions-item v-for="row in previewRows" :key="row.label" :label="row.label">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
            <h4 class="preview-section-title">{{ t('edit.configRestorePreviewTasks') }}</h4>
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
            <a-empty v-else :description="t('edit.configRestorePreviewNoTasks')" />
          </template>
          <a-empty v-else :description="t('edit.configRestorePreviewEmpty')" />
        </template>
        <!-- 脚本级：实例列表可展开查看账号/任务明细 -->
        <template v-else>
          <a-empty
            v-if="!previewData.instances.length"
            :description="t('edit.configRestorePreviewEmpty')"
          />
          <a-collapse v-else class="preview-instance-list" :bordered="false">
            <a-collapse-panel v-for="inst in previewData.instances" :key="inst.idx">
              <template #header>
                <span class="preview-instance-name">
                  {{ `${String(inst.idx).padStart(2, '0')} - ${inst.name}` }}
                </span>
                <a-tag v-if="inst.active" color="blue">
                  {{ t('edit.configRestorePreviewActive') }}
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
              {{ `${t('edit.configRestoreBackupFiles')} (${previewFiles.length})` }}
            </span>
          </template>
          <div class="preview-file-list">
            <button
              v-for="f in previewFiles"
              :key="f.path"
              type="button"
              class="preview-file-link"
              @click="openBackupFile(f)"
            >
              <span class="preview-file-path">{{ f.path }}</span>
              <span class="preview-file-size">{{ formatFileSize(f.size) }}</span>
            </button>
          </div>
        </a-collapse-panel>
      </a-collapse>
    </a-spin>
    <template #footer>
      <!-- 操作按钮常驻弹窗底部（footer 不随 body 滚动）；「查看详细配置」
           依赖父组件的 onDetail 回调（恢复 + 拉起查看会话），专项未提供时
           不渲染，避免出现无响应的按钮 -->
      <div class="preview-actions">
        <a-tooltip
          v-if="onDetail"
          :title="t('edit.configRestoreDetailHint', { script: scriptName })"
        >
          <a-button :disabled="disabled" @click="handlePreviewDetail">
            {{ t('edit.configRestoreDetailView') }}
          </a-button>
        </a-tooltip>
        <a-button @click="previewOpen = false">
          {{ t('edit.close') }}
        </a-button>
      </div>
    </template>
  </a-modal>

  <!-- ══ 备份文件内容（只读；等宽原文 + 复制）══ -->
  <a-modal
    :open="fileOpen"
    :footer="null"
    width="720px"
    :body-style="{ maxHeight: '65vh', overflowY: 'auto' }"
    @update:open="fileOpen = $event"
  >
    <template #title>
      <div class="file-modal-title">
        <span class="file-modal-path">{{ fileItem?.path }}</span>
        <a-button type="text" size="small" @click="copyFileContent">
          {{ t('edit.configRestoreCopy') }}
        </a-button>
      </div>
    </template>
    <a-spin :spinning="fileLoading">
      <p v-if="fileError" class="restore-desc">{{ fileError }}</p>
      <pre v-else class="backup-file-content">{{ fileContent }}</pre>
    </a-spin>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { buildRestoreConfirm, sourceLabelKey, sourceTagColor } from '@/utils/configRestoreMode'

const { t } = useI18n()

/**
 * 通用配置恢复组件：MAS 用户配置（在前）与 {script} 原生配置（在后）两类备份的
 * 列表 / 预览 / 查看详细 / 一键恢复。API 由父组件注入（脚本/用户上下文已闭包
 * 捕获），文案中 {script} 用 scriptName 参数化——其他适配器传参即可套用。
 */
const props = defineProps<{
  /** 弹窗开关（v-model） */
  open: boolean
  /** 配置写入锁定（任务运行中禁用恢复与查看详细） */
  disabled?: boolean
  /** 脚本名（文案参数化用，如「一条龙」） */
  scriptName: string
  /** 目标池：顺序即 segmented 展示顺序（MAS 在前脚本在后） */
  targets: Array<{ key: string; kind: 'user' | 'script' }>
  /** 后端 API：list/preview/restore（父组件按自身端点包装） */
  api: {
    list: (target: string) => Promise<{
      code?: number
      message?: string
      data?: Array<{ time: string; mode?: string | null }>
      /** 当前配置来源（仅三态专项返回；据此比对是否需要跨来源提示） */
      mode?: string | null
    }>
    preview: (
      target: string,
      time: string
    ) => Promise<{
      code?: number
      message?: string
      info?: { key: string; value: string }[]
      account?: { key: string; value: string }[]
      tasks?: { app_id: string; app_name: string; enabled: boolean }[]
      instances?: {
        idx: number
        name: string
        active: boolean
        account: { key: string; value: string }[]
        tasks: { app_id: string; app_name: string; enabled: boolean }[]
      }[]
      /** 通用端点把专项载荷包在 data 里；缺省回落到顶层平铺结构 */
      data?: Record<string, unknown> | null
    }>
    restore: (
      target: string,
      time: string
    ) => Promise<{
      code?: number
      message?: string
    }>
    /** 只读读取备份内文本文件（预览「备份文件」点击查看；未提供时点击提示） */
    readFile?: (
      target: string,
      time: string,
      path: string
    ) => Promise<{
      code?: number
      message?: string
      path?: string
      size?: number
      content?: string
    }>
  }
  /** 预览字段标签映射（key → 展示标题） */
  fieldLabels?: Record<string, string>
  /** 描述文案覆写（缺省用 i18n 通用词条；专项的归档时机措辞不同时传入） */
  userDesc?: string
  scriptDesc?: string
  /** 预览字段值格式化（枚举值转词表文案） */
  formatValue?: (key: string, raw: string) => string
  /** 恢复后回调（一键恢复成功后通知父组件刷新表单等） */
  onRestored?: (target: string, item: { time: string }) => void
  /** 查看详细配置回调（父组件执行恢复 + 拉起脚本查看会话）。
      第三个参数为当前配置来源（仅三态专项非空），供专项比对跨来源并追加提示。
      返回 ``Promise<boolean>``（true=已恢复）——组件据此决定预览弹窗是否关闭，
      取消/失败保持预览打开。 */
  onDetail?: (
    target: string,
    item: { time: string; mode?: string | null },
    currentMode?: string | null
  ) => Promise<boolean>
}>()

const emit = defineEmits<{
  (e: 'update:open', val: boolean): void
}>()

const onOpenChange = (val: boolean) => {
  emit('update:open', val)
}

// ══ 目标池 ══
const restoreTarget = ref(props.targets[0]?.key ?? '')

const currentTarget = computed(
  () => props.targets.find(item => item.key === restoreTarget.value) ?? props.targets[0]
)

const targetOptions = computed(() =>
  props.targets.map(tgt => ({
    label:
      tgt.kind === 'user'
        ? t('edit.configRestoreTargetMas')
        : t('edit.configRestoreTargetScript', { script: props.scriptName }),
    value: tgt.key,
  }))
)

// ══ 备份列表 ══
interface BackupItem {
  time: string
  /** 备份时点的配置来源（脚本/用户/直控）；无标注为 null */
  mode?: string | null
}

const backups = ref<BackupItem[]>([])
const backupsLoading = ref(false)
/** 当前配置来源（仅三态专项非空）：与备份标签比对决定是否提示跨来源 */
const currentSource = ref<string | null>(null)

const formatBackupTime = (ts: string) =>
  `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`

/** 配置来源标签（备份时点 Info.Mode → 文案与标签色）；未知值按用户级兜底 */
const modeTag = (mode: string): { label: string; color: string } => ({
  label: t(sourceLabelKey(mode)),
  color: sourceTagColor(mode),
})

const loadBackups = async () => {
  backupsLoading.value = true
  try {
    const resp = await props.api.list(restoreTarget.value)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.configRestoreListFailed'))
    }
    backups.value = resp.data ?? []
    currentSource.value = resp.mode ?? null
  } catch (e) {
    // 失败时清空列表与当前来源：残留上一次（可能是切 target 前）的数据
    // 会诱导用户对着过期列表做恢复判断
    backups.value = []
    currentSource.value = null
    message.error(e instanceof Error ? e.message : t('edit.configRestoreListFailed'))
  } finally {
    backupsLoading.value = false
  }
}

watch(restoreTarget, () => {
  if (props.open) void loadBackups()
})

watch(
  () => props.open,
  val => {
    if (val) void loadBackups()
  }
)

// ══ 预览 ══
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const previewTime = ref('')
const previewItem = ref<BackupItem | null>(null)
// 预览响应原文：内置 info/account/tasks/instances 之外的自定义预览
// 结构通过 #preview 插槽的 raw 取用
const previewRaw = ref<unknown>(null)

const previewData = reactive<{
  info: { key: string; value: string }[]
  account: { key: string; value: string }[]
  tasks: { app_id: string; app_name: string; enabled: boolean }[]
  instances: {
    idx: number
    name: string
    active: boolean
    account: { key: string; value: string }[]
    tasks: { app_id: string; app_name: string; enabled: boolean }[]
  }[]
}>({
  info: [],
  account: [],
  tasks: [],
  instances: [],
})

const fieldLabel = (key: string): string => props.fieldLabels?.[key] ?? key
const formatValue = (key: string, raw: string): string =>
  props.formatValue?.(key, raw) ?? (raw || '—')

// 用户级摘要展示顺序：基本信息（信息字段 + 账号字段）→ 任务配置
const previewRows = computed(() => {
  const info = new Map(previewData.info.map(f => [f.key, f.value]))
  const account = new Map(previewData.account.map(f => [f.key, f.value]))
  const rows: { label: string; value: string }[] = []
  const order: Array<{ key: string; label: string; src: 'info' | 'account' }> = [
    { key: 'name', label: t('edit.username'), src: 'info' },
    { key: 'status', label: t('edit.enabled'), src: 'info' },
    { key: 'mode', label: t('edit.configRestorePreviewMode'), src: 'info' },
    { key: 'launcher_mode', label: t('edit.configRestorePreviewLauncher'), src: 'info' },
    { key: 'game_region', label: t('edit.configRestorePreviewRegion'), src: 'account' },
    { key: 'game_path', label: t('edit.configRestorePreviewGamePath'), src: 'account' },
    { key: 'game_language', label: t('edit.configRestorePreviewLanguage'), src: 'account' },
    { key: 'account', label: t('edit.configRestorePreviewAccount'), src: 'account' },
    { key: 'password', label: t('edit.configRestorePreviewPassword'), src: 'account' },
    {
      key: 'bilibili_account_name',
      label: t('edit.configRestorePreviewBilibili'),
      src: 'account',
    },
    {
      key: 'use_custom_win_title',
      label: t('edit.configRestorePreviewUseCustomWinTitle'),
      src: 'account',
    },
    {
      key: 'custom_win_title',
      label: t('edit.configRestorePreviewCustomWinTitle'),
      src: 'account',
    },
    { key: 'remained_day', label: t('edit.daysLeft'), src: 'info' },
    { key: 'notes', label: t('edit.note'), src: 'info' },
    { key: 'push_log_mode', label: t('edit.collectNodeDetails'), src: 'info' },
  ]
  for (const spec of order) {
    const raw = spec.src === 'info' ? info.get(spec.key) : account.get(spec.key)
    if (raw === undefined) continue
    rows.push({ label: spec.label, value: formatValue(spec.key, raw) })
  }
  return rows
})

const handlePreview = async (item: BackupItem) => {
  previewOpen.value = true
  previewLoading.value = true
  previewError.value = ''
  previewTime.value = formatBackupTime(item.time)
  previewItem.value = item
  try {
    const resp = await props.api.preview(restoreTarget.value, item.time)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.configRestorePreviewFailed'))
    }
    // 通用端点把专项载荷包在 data 里；缺省回落到顶层平铺结构（向后兼容）
    const payload = (resp.data ?? resp) as typeof resp
    previewData.info = payload.info ?? []
    previewData.account = payload.account ?? []
    previewData.tasks = payload.tasks ?? []
    previewData.instances = payload.instances ?? []
    previewRaw.value = payload
  } catch (e) {
    previewError.value = e instanceof Error ? e.message : t('edit.configRestorePreviewFailed')
    previewData.info = []
    previewData.account = []
    previewData.tasks = []
    previewData.instances = []
    previewRaw.value = null
  } finally {
    previewLoading.value = false
  }
}

// 预览弹窗内「查看详细配置」：走父组件详情动作（带备份来源与当前来源）。
// 确认/恢复成功后才关预览——取消或失败时保持预览打开，避免重看要重新点开
const handlePreviewDetail = async () => {
  if (props.disabled || !previewItem.value) return
  const restored = await props.onDetail?.(
    restoreTarget.value,
    previewItem.value,
    currentSource.value
  )
  if (restored !== false) previewOpen.value = false
}

// ══ 备份文件（预览载荷标准 files 字段；点击查看原始内容）══
interface BackupFileItem {
  path: string
  size: number
}

const previewFiles = computed<BackupFileItem[]>(() => {
  const raw = previewRaw.value as { files?: BackupFileItem[] } | null
  // 只渲染标准条目（path+size）；专项自定义摘要卡用其它键名（fileCards），
  // 由专项 #preview 插槽自行渲染
  return (raw?.files ?? []).filter(f => typeof f?.path === 'string')
})

const formatFileSize = (size: number): string => {
  if (!Number.isFinite(size) || size < 0) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

const fileOpen = ref(false)
const fileLoading = ref(false)
const fileError = ref('')
const fileItem = ref<BackupFileItem | null>(null)
const fileContent = ref('')

const openBackupFile = async (item: BackupFileItem) => {
  if (!previewItem.value) return
  fileOpen.value = true
  fileLoading.value = true
  fileError.value = ''
  fileItem.value = item
  fileContent.value = ''
  try {
    if (!props.api.readFile) {
      throw new Error(t('edit.configRestoreFileUnsupported'))
    }
    const resp = await props.api.readFile(restoreTarget.value, previewItem.value.time, item.path)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.configRestoreFileFailed'))
    }
    fileContent.value = resp.content ?? ''
  } catch (e) {
    fileError.value = e instanceof Error ? e.message : t('edit.configRestoreFileFailed')
  } finally {
    fileLoading.value = false
  }
}

const copyFileContent = async () => {
  if (!fileContent.value) return
  try {
    await navigator.clipboard.writeText(fileContent.value)
    message.success(t('edit.configRestoreCopied'))
  } catch {
    message.error(t('edit.configRestoreFileFailed'))
  }
}

// ══ 一键恢复 ══
const runRestore = async (item: BackupItem) => {
  if (props.disabled) {
    throw new Error(t('edit.configLocked'))
  }
  const resp = await props.api.restore(restoreTarget.value, item.time)
  if (resp.code !== 200) {
    throw new Error(resp.message || t('edit.configRestoreFailed'))
  }
  return resp
}

const finishRestore = async (item: BackupItem) => {
  message.success(t('edit.configRestoreSuccess'))
  props.onRestored?.(restoreTarget.value, item)
  await loadBackups()
}

/** 恢复确认（单弹窗）：跨来源时换标题并追加来源切换说明，确认后由基座切来源再恢复 */
const confirmRestore = (item: BackupItem) => {
  if (props.disabled) return
  const { title, paragraphs } = buildRestoreConfirm(
    t,
    { title: t('edit.configRestoreConfirmTitle'), desc: t('edit.configRestoreConfirmDesc') },
    item.mode,
    currentSource.value
  )
  Modal.confirm({
    title,
    content: h(
      'div',
      paragraphs.map(text =>
        h('p', { style: { color: 'var(--ant-color-error)', margin: '0 0 8px' } }, text)
      )
    ),
    okText: t('edit.configRestoreAction'),
    okType: 'danger',
    onOk: async () => {
      try {
        await runRestore(item)
        await finishRestore(item)
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
      }
    },
  })
}
</script>

<style scoped>
.restore-lock-alert {
  margin-bottom: 12px;
}

.restore-target-switch {
  margin-bottom: 12px;
}

/* 恢复目标分段器：低频工具内的选择，选中态只用中性灰填充与主文字色 */
.restore-target-switch :deep(.ant-segmented-item-selected) {
  background: var(--ant-color-fill-secondary);
  box-shadow: none;
}

.restore-target-switch :deep(.ant-segmented-item-selected .ant-segmented-item-label) {
  color: var(--ant-color-text);
}

.restore-desc {
  margin: 0 0 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 当前配置来源：与描述同段换行展示，供用户比对各备份的来源标签 */
.restore-current-source {
  display: block;
  margin-top: 2px;
}

.backup-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.backup-time {
  color: var(--ant-color-text-secondary);
  font-variant-numeric: tabular-nums;
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

/* 文件内容弹窗：标题路径 + 复制按钮；正文等宽原文 */
.file-modal-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-right: 24px;
}

.file-modal-path {
  font-size: 14px;
  word-break: break-all;
}

.backup-file-content {
  margin: 0;
  padding: 12px;
  border-radius: 6px;
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text);
  font-family: var(--font-monospace, 'Consolas', 'Monaco', monospace);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.preview-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
