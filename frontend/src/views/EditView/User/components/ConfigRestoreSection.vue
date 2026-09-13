<template>
  <!-- ══ 配置恢复（历史备份浏览 / 预览 / 查看详细 / 一键恢复；MAS 在前脚本在后）══ -->
  <a-modal
    :open="open"
    :title="t('edit.configRestoreTitle')"
    :footer="null"
    width="520px"
    @update:open="onOpenChange"
  >
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
    </p>
    <a-spin :spinning="backupsLoading">
      <a-empty v-if="!backups.length" :description="t('edit.configRestoreEmpty')" />
      <a-list v-else :data-source="backups" size="small" row-key="time">
        <template #renderItem="{ item }">
          <a-list-item>
            <span class="backup-time">{{ formatBackupTime(item.time) }}</span>
            <a-space>
              <a-button type="link" size="small" @click="handlePreview(item)">
                {{ t('edit.configRestorePreview') }}
              </a-button>
              <a-button size="small" @click="confirmRestore(item)">
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
    :footer="null"
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
    <a-spin :spinning="previewLoading" class="preview-scroll">
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
        <!-- 用户级：基本信息 + 账号 + 任务编排 -->
        <template v-if="currentTarget?.kind === 'user'">
          <h4 class="preview-section-title">{{ t('edit.basicInfo') }}</h4>
          <a-descriptions :column="1" size="small" bordered class="preview-box">
            <a-descriptions-item
              v-for="row in previewRows"
              :key="row.label"
              :label="row.label"
            >
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
              <a-descriptions
                :column="1"
                size="small"
                bordered
                class="preview-box"
              >
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
    </a-spin>
    <div class="preview-actions">
      <!-- 「查看详细配置」依赖父组件的 onDetail 回调（恢复 + 拉起查看会话）；
           专项未提供时不渲染，避免出现无响应的按钮 -->
      <a-tooltip
        v-if="onDetail"
        :title="t('edit.configRestoreDetailHint', { script: scriptName })"
      >
        <a-button @click="handlePreviewDetail">
          {{ t('edit.configRestoreDetailView') }}
        </a-button>
      </a-tooltip>
      <a-button @click="previewOpen = false">
        {{ t('edit.close') }}
      </a-button>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'

const { t } = useI18n()

/**
 * 通用配置恢复组件：MAS 用户配置（在前）与 {script} 原生配置（在后）两类备份的
 * 列表 / 预览 / 查看详细 / 一键恢复。API 由父组件注入（脚本/用户上下文已闭包
 * 捕获），文案中 {script} 用 scriptName 参数化——其他适配器传参即可套用。
 */
const props = defineProps<{
  /** 弹窗开关（v-model） */
  open: boolean
  /** 脚本名（文案参数化用，如「一条龙」） */
  scriptName: string
  /** 目标池：顺序即 segmented 展示顺序（MAS 在前脚本在后） */
  targets: Array<{ key: string; kind: 'user' | 'script' }>
  /** 后端 API：list/preview/restore（父组件按自身端点包装） */
  api: {
    list: (
      target: string
    ) => Promise<{
      code?: number
      message?: string
      data?: Array<{ time: string }>
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
    ) => Promise<{ code?: number; message?: string }>
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
  /** 查看详细配置回调（父组件执行恢复 + 拉起脚本查看会话） */
  onDetail?: (target: string, item: { time: string }) => void
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
}

const backups = ref<BackupItem[]>([])
const backupsLoading = ref(false)

const formatBackupTime = (ts: string) =>
  `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`

const loadBackups = async () => {
  backupsLoading.value = true
  try {
    const resp = await props.api.list(restoreTarget.value)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.configRestoreListFailed'))
    }
    backups.value = resp.data ?? []
  } catch (e) {
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
    previewError.value =
      e instanceof Error ? e.message : t('edit.configRestorePreviewFailed')
    previewData.info = []
    previewData.account = []
    previewData.tasks = []
    previewData.instances = []
    previewRaw.value = null
  } finally {
    previewLoading.value = false
  }
}

// 预览弹窗内「查看详细配置」：关掉预览，走父组件详情动作
const handlePreviewDetail = () => {
  if (!previewItem.value) return
  previewOpen.value = false
  props.onDetail?.(restoreTarget.value, previewItem.value)
}

// ══ 一键恢复 ══
const doRestore = async (item: BackupItem) => {
  const resp = await props.api.restore(restoreTarget.value, item.time)
  if (resp.code !== 200) {
    throw new Error(resp.message || t('edit.configRestoreFailed'))
  }
  message.success(t('edit.configRestoreSuccess'))
}

const confirmRestore = (item: BackupItem) => {
  Modal.confirm({
    title: t('edit.configRestoreConfirmTitle'),
    content: h(
      'p',
      { style: { color: 'var(--ant-color-error)', margin: 0 } },
      t('edit.configRestoreConfirmDesc')
    ),
    okText: t('edit.configRestoreAction'),
    okType: 'danger',
    onOk: async () => {
      try {
        await doRestore(item)
        props.onRestored?.(restoreTarget.value, item)
        await loadBackups()
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
      }
    },
  })
}
</script>

<style scoped>
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

.backup-time {
  color: var(--ant-color-text-secondary);
  font-variant-numeric: tabular-nums;
}

/* 预览内容限高在弹窗内滚动，摘要过长不撑破窗口 */
.preview-scroll {
  max-height: 56vh;
  overflow-y: auto;
}

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

.preview-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}
</style>
