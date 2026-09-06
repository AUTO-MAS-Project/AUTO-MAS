<template>
  <div
    class="bgi-project-editor"
    :class="{ 'bgi-project-editor-disabled': !editable }"
    @click.capture="handleBlankClick"
  >
    <!-- 工具栏：添加脚本 / 删除脚本（仅配置组可编辑且非单项目虚拟组） -->
    <div v-if="isScriptGroup && editable" class="bgi-project-toolbar">
      <a-space size="small">
        <a-button size="small" type="primary" ghost :disabled="!editable" @click="emit('add-script')">
          <template #icon><PlusOutlined /></template>
          {{ t('edit.bettergiProjectAddScript') }}
        </a-button>
        <a-popconfirm
          :title="t('edit.bettergiProjectRemoveConfirm')"
          :ok-text="t('edit.ok')"
          :cancel-text="t('edit.cancel')"
          :disabled="!selectedDeleteUids.size"
          @confirm="removeSelectedProjects"
        >
          <a-button size="small" danger :disabled="!selectedDeleteUids.size">
            <template #icon><DeleteOutlined /></template>
            {{ t('edit.bettergiProjectRemoveScript') }}
          </a-button>
        </a-popconfirm>
      </a-space>
      <span class="bgi-project-toolbar-tip">{{ t('edit.bettergiProjectToolbarTip') }}</span>
    </div>

    <!-- 多选操作提示条（Ctrl 逐个 / Shift 区间，选中超过 1 行时显示） -->
    <div v-if="hasMultiSelection" class="bgi-project-multi-hint">
      <a-tag color="processing" size="small">
        {{ t('edit.bettergiMultiSelected', { count: selectedDeleteUids.size }) }}
      </a-tag>
      <span>{{ t('edit.bettergiProjectMultiHint') }}</span>
      <a-button size="small" type="link" @click="clearSelection">
        {{ t('edit.bettergiProjectClearSelection') }}
      </a-button>
    </div>

    <!-- 项目列表（配置组=json 内 projects；JS/路径=单项目虚拟组），可拖拽排序 -->
    <a-spin :spinning="loading" size="small">
      <template v-if="!loading">
        <div v-if="projects.length" class="bgi-project-list">
          <draggable
            v-model="projectsModel"
            :item-key="projRowKey"
            handle=".bgi-project-drag-area"
            :animation="200"
            :disabled="!isSortable"
            ghost-class="bgi-project-ghost"
            chosen-class="bgi-project-chosen"
            drag-class="bgi-project-drag"
            class="bgi-project-sort-list"
            @end="persistProjects()"
          >
            <template #item="{ element, index }">
              <div
                class="bgi-project-row"
                :class="{
                  'bgi-project-row-disabled': !editable,
                  'bgi-project-row-selected': isRowSelected(element),
                }"
                :title="t('edit.bettergiProjectRowTip')"
                @click="handleRowClick(element, index, $event)"
                @dblclick.stop="openProjectSettings(element, index)"
              >
                <!-- 拖拽热区：可编辑配置组覆盖整行左侧 2/3；JS/路径单行（无可选）占满 -->
                <div class="bgi-project-drag-area" :class="{ 'bgi-project-drag-area-full': !selectable }">
                  <HolderOutlined
                    v-if="isSortable"
                    class="bgi-project-drag-handle"
                    aria-hidden="true"
                  />
                  <span v-else class="bgi-project-drag-spacer" aria-hidden="true"></span>
                  <span class="bgi-project-name">{{ element.name || element.folderName || element.key || '—' }}</span>
                  <span v-if="element.folderName" class="bgi-project-folder">{{ element.folderName }}</span>
                </div>
                <div v-if="selectable" class="bgi-project-row-state">
                  <button
                    v-if="isRowSelected(element)"
                    type="button"
                    class="bgi-project-row-unselect"
                    :title="t('edit.bettergiProjectUnselect')"
                    :aria-label="t('edit.bettergiProjectUnselect')"
                    @click.stop="unselectRow(element)"
                    @dblclick.stop
                  >
                    <CheckCircleFilled class="bgi-project-row-selected-icon" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </template>
          </draggable>
        </div>
        <div v-else class="bgi-project-empty">
          <a-empty :description="t('edit.bettergiProjectEmpty')" />
        </div>
      </template>
    </a-spin>

    <p v-if="projects.length && !(isScriptGroup && editable)" class="bgi-project-tip">
      {{ t('edit.bettergiProjectListTip') }}
    </p>

    <!-- 双击项目：设置弹窗（脚本配置 / 脚本说明 标签页）。
         后打开的弹窗显示在之前弹窗之上：显式给 z-index 高于外层放大弹窗(1000) -->
    <a-modal
      v-model:open="settingsModal.open"
      :title="settingsModal.title"
      :ok-text="t('edit.bettergiProjectSettingsSave')"
      :cancel-text="t('edit.cancel')"
      :confirm-loading="settingsModal.saving"
      width="720px"
      :z-index="1100"
      class="bgi-project-settings-modal"
      :ok-button-props="{ disabled: props.kind !== 'scriptgroup' }"
      @ok="saveProjectSettings"
      @cancel="settingsModal.open = false"
    >
      <a-tabs v-model:activeKey="settingsTab" size="small" class="bgi-project-settings-tabs">
        <!-- Tab1：脚本配置 -->
        <a-tab-pane key="config" :tab="t('edit.bettergiProjectConfigTab')">
          <a-spin :spinning="settingsModal.loading" size="small">
            <template v-if="settingsModal.items.length">
              <div class="bgi-project-settings-fields">
                <template v-for="(item, idx) in settingsModal.items" :key="item.name || idx">
                  <!-- 分隔线 -->
                  <div
                    v-if="item.type === 'separator'"
                    class="bgi-project-separator"
                    :class="{ 'bgi-project-separator-first': idx === 0 }"
                  >
                    {{ item.label || '' }}
                  </div>
                  <!-- checkbox -->
                  <div v-else-if="item.type === 'checkbox'" class="bgi-project-setting-row">
                    <span class="bgi-project-setting-label">{{ item.label }}</span>
                    <a-switch
                      :checked="Boolean(fieldValue(item.name))"
                      @change="(v: boolean | string | number) => setField(item.name, Boolean(v))"
                    />
                  </div>
                  <!-- select -->
                  <div v-else-if="item.type === 'select'" class="bgi-project-setting-row">
                    <span class="bgi-project-setting-label">{{ item.label }}</span>
                    <a-select
                      :value="String(fieldValue(item.name) ?? '')"
                      :options="item.options?.map((o: string) => ({ label: o, value: o })) || []"
                      :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                      allow-clear
                      @change="(v: unknown) => setField(item.name, v == null ? '' : String(v))"
                    />
                  </div>
                  <!-- multi-checkbox -->
                  <div v-else-if="item.type === 'multi-checkbox'" class="bgi-project-setting-row">
                    <span class="bgi-project-setting-label">{{ item.label }}</span>
                    <a-select
                      mode="multiple"
                      :value="fieldListValue(item.name)"
                      :options="item.options?.map((o: string) => ({ label: o, value: o })) || []"
                      :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                      @change="(v: unknown) => setField(item.name, Array.isArray(v) ? v : [])"
                    />
                  </div>
                  <!-- input-text / 其它一律文本 -->
                  <div v-else class="bgi-project-setting-row">
                    <span class="bgi-project-setting-label">{{ item.label }}</span>
                    <a-input
                      :value="String(fieldValue(item.name) ?? '')"
                      @change="(e: Event) => setField(item.name, (e.target as HTMLInputElement).value)"
                    />
                  </div>
                </template>
              </div>
            </template>
            <div v-else class="bgi-project-settings-empty">
              <a-empty :description="t('edit.bettergiProjectNoSettingsFile')" />
            </div>
          </a-spin>
        </a-tab-pane>

        <!-- Tab2：脚本说明（README） -->
        <a-tab-pane key="readme" :tab="t('edit.bettergiProjectReadmeTab')">
          <div v-if="settingsModal.readme" class="bgi-project-readme">
            <pre>{{ settingsModal.readme }}</pre>
          </div>
          <div v-else class="bgi-project-settings-empty">
            <a-empty :description="t('edit.bettergiProjectReadmeEmpty')" />
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { CheckCircleFilled, DeleteOutlined, HolderOutlined, PlusOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { BetterGiService } from '@/api'
import type {
  BetterGIScriptGroupSaveIn,
  BetterGIScriptGroupDetailOut,
} from '@/api'

const { t } = useI18n()

// BGI 项目行来源类型（加载时注入 _uid 供选择删除；保存时剔除该字段）
type ProjectRow = {
  name?: string
  folderName?: string
  key?: string
  index?: number
  jsScriptSettingsObject?: Record<string, unknown>
  [k: string]: unknown
}

const props = withDefaults(
  defineProps<{
    scriptId: string
    userId: string
    /** 配置组名（scriptgroup 时=json 文件名；JS/路径时=行名/脚本目录名） */
    groupName: string
    /** 来源类型：scriptgroup=读 json projects；js/pathing=单项目虚拟组 */
    kind: 'scriptgroup' | 'js' | 'pathing' | string
    /** JS 独立脚本目录名（双击弹设置用）；pathing 无 setting 文件 */
    folderName?: string
    /** 可读显示名（js 取 manifest 名 / pathing 取文件名末段；scriptgroup 不传用组名） */
    displayName?: string
    editable?: boolean
  }>(),
  {
    folderName: '',
    displayName: '',
    editable: false,
  }
)

const emit = defineEmits<{ (e: 'add-script'): void }>()

const logger = window.electronAPI.getLogger('BetterGI配置组项目编辑')

const loading = ref(false)
const saving = ref(false)

const isScriptGroup = computed<boolean>(() => props.kind === 'scriptgroup')
// 可选择（Shift/Ctrl 多选）：仅可编辑配置组
const selectable = computed<boolean>(() => isScriptGroup.value && props.editable)
// 可拖拽排序：配置组 json 且至少两个项目
const isSortable = computed<boolean>(
  () => selectable.value && projects.value.length > 1
)

// 当前编辑的完整配置组 json（scriptgroup 时保存整份；js/pathing 无 json 载体）
const groupJson = ref<Record<string, any>>({})
const projects = ref<ProjectRow[]>([])
// 选中待删除的 _uid 集合
const selectedDeleteUids = ref<Set<number>>(new Set())

const settingsModal = reactive({
  open: false,
  loading: false,
  saving: false,
  title: '',
  items: [] as Array<Record<string, any>>,
  readme: '',
  values: {} as Record<string, unknown>,
  // 定位：scriptgroup 中该 project 在 projects 数组的位置（js/pathing 为空）
  projectIndex: -1 as number,
})

let projectSeq = 0

// 供 vuedraggable v-model（纯前端顺序；保存由 @end 触发）
const projectsModel = computed<ProjectRow[]>({
  get: () => projects.value,
  set: value => {
    projects.value = value
  },
})

// ---- Shift/Ctrl 鼠标多选（与左栏一条龙交互一致）----
// 选中集合按 _uid 记录；_uid 在行加载时生成且拖拽/保存不变化，可稳定定位。
const isRowSelected = (row: ProjectRow): boolean =>
  typeof row._uid === 'number' && selectedDeleteUids.value.has(row._uid)

// Shift 区间选择的锚点行 uid（普通/Ctrl 点击时更新）
const multiAnchorUid = ref<number>(-1)

// 当前多选中的行（按 projects 顺序）
const selectedRows = computed<ProjectRow[]>(() =>
  projects.value.filter(r => typeof r._uid === 'number' && selectedDeleteUids.value.has(r._uid))
)
// 是否处于多选状态（多于 1 行时展示批量操作提示条）
const hasMultiSelection = computed<boolean>(() => selectedRows.value.length > 1)

// 清空多选（切换配置组/重载时调用）
const clearSelection = () => {
  selectedDeleteUids.value = new Set()
  multiAnchorUid.value = -1
}

// 点击右侧打勾按钮：取消该行选中（从选中集合移除；锚点同步复位）
const unselectRow = (row: ProjectRow) => {
  if (!props.editable || !isScriptGroup.value) return
  const uid = row._uid
  if (typeof uid !== 'number') return
  const next = new Set(selectedDeleteUids.value)
  next.delete(uid)
  selectedDeleteUids.value = next
  if (multiAnchorUid.value === uid) multiAnchorUid.value = -1
}

// 点击编辑器空白处（非项目行、非工具栏按钮/提示区）取消选中
const handleBlankClick = (event: MouseEvent) => {
  if (!props.editable || !isScriptGroup.value) return
  const target = event.target as HTMLElement
  if (target.closest('.bgi-project-row')) return
  if (target.closest('.bgi-project-toolbar')) return
  if (target.closest('.bgi-project-multi-hint')) return
  if (selectedDeleteUids.value.size) clearSelection()
}

// 行点击：普通=单选该行（并作为后续 Shift 锚点）；
// Ctrl/Cmd=逐个切换多选；Shift=从锚点行到当前行区间多选。
// 双击（打开设置弹窗）由 dblclick 独立处理，不参与多选。
const handleRowClick = (row: ProjectRow, index: number, event: MouseEvent) => {
  if (!props.editable || !isScriptGroup.value) return
  const uid = row._uid
  if (typeof uid !== 'number') return
  if (event.shiftKey) {
    // Shift 区间选择：锚点 uid 定位锚点行；按当前列表顺序圈选锚点行到当前行
    const anchorIndex = projects.value.findIndex(r => r._uid === multiAnchorUid.value)
    if (anchorIndex < 0) {
      // 无锚点（会话内首次点击即 Shift）：以当前行为锚点，单选当前行
      multiAnchorUid.value = uid
      selectedDeleteUids.value = new Set([uid])
      return
    }
    const lo = Math.min(anchorIndex, index)
    const hi = Math.max(anchorIndex, index)
    const uids = new Set<number>()
    for (let i = lo; i <= hi; i += 1) {
      const itemUid = projects.value[i]?._uid
      if (typeof itemUid === 'number') uids.add(itemUid)
    }
    selectedDeleteUids.value = uids
    return
  }
  if (event.ctrlKey || event.metaKey) {
    multiAnchorUid.value = uid
    const next = new Set(selectedDeleteUids.value)
    if (next.has(uid)) next.delete(uid)
    else next.add(uid)
    selectedDeleteUids.value = next
    return
  }
  // 普通点击：清空多选集合，但保留当前行为后续 Shift 的锚点
  selectedDeleteUids.value = new Set([uid])
  multiAnchorUid.value = uid
}

const reload = async () => {
  if (!isScriptGroup.value || !props.groupName || !props.userId) {
    // JS/路径：单项目虚拟组（项目名=显示名；folder 供双击读设置）
    if (props.kind === 'js' || props.kind === 'pathing') {
      clearSelection()
      projects.value = [
        {
          name: props.displayName || props.groupName,
          folderName: props.folderName || undefined,
          key: props.groupName,
          _uid: ++projectSeq,
        },
      ]
    }
    return
    }
  loading.value = true
  try {
    const resp: BetterGIScriptGroupDetailOut =
      await BetterGiService.getBettergiScriptGroupDetailApiApiScriptsBettergiScriptGroupDetailGet(
        props.scriptId,
        props.userId,
        props.groupName
      )
    if (resp.code !== 200) {
      message.warning(resp.message || t('edit.bettergiProjectLoadFailed'))
      projects.value = []
      groupJson.value = {}
      return
    }
    const data = resp.data || {}
    groupJson.value = data
    const list = Array.isArray(data.projects) ? data.projects : []
    projects.value = list.map(item => ({ ...item, _uid: ++projectSeq }))
    clearSelection()
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : t('edit.bettergiProjectLoadFailed'))
    projects.value = []
    groupJson.value = {}
  } finally {
    loading.value = false
  }
}

// 拖拽排序结束 / 各保存路径统一写回 per-user 副本；写前规范化 index 并剔除 _uid
const persistProjects = async () => {
  if (!isScriptGroup.value || saving.value) return
  saving.value = true
  try {
    const rows = projects.value.map((item, idx) => {
      const { _uid: _removed, ...rest } = item as ProjectRow & { _uid?: number }
      void _removed
      return { ...rest, index: idx + 1 }
    })
    const body: BetterGIScriptGroupSaveIn = {
      scriptId: props.scriptId,
      userId: props.userId,
      name: props.groupName,
      data: {
        ...groupJson.value,
        projects: rows,
      },
    }
    const resp =
      await BetterGiService.saveBettergiScriptGroupApiApiScriptsBettergiScriptGroupSavePost(
        body
      )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.bettergiProjectSaveFailed'))
    }
    groupJson.value = { ...groupJson.value, projects: rows }
    message.success(t('edit.bettergiProjectSaved'))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : t('edit.bettergiProjectSaveFailed'))
  } finally {
    saving.value = false
  }
}

// 父组件「添加配置组弹窗(冻结配置组标签)」确认后调用：把 JS/路径行追加到末尾并保存
const addProjects = async (rows: ProjectRow[]) => {
  if (!isScriptGroup.value || !rows.length) return
  const next = projects.value.map(item => ({ ...item }))
  for (const row of rows) {
    const { _uid: _removed, ...rest } = row as ProjectRow & { _uid?: number }
    void _removed
    next.push({ ...rest, _uid: ++projectSeq })
  }
  projects.value = next
  await persistProjects()
  clearSelection()
}

// 删除选中行（多选 + 「删除脚本」确认后）
const removeSelectedProjects = async () => {
  if (!isScriptGroup.value) return
  const keep = projects.value.filter(r => !isRowSelected(r))
  if (keep.length === projects.value.length) return
  projects.value = keep
  clearSelection()
  await persistProjects()
}

const projRowKey = (proj: ProjectRow, index: number): string => {
  const base = proj.folderName
    ? proj.folderName
    : String(proj.name || proj.key || '')
  return `${props.kind}:${base}:${index}`
}

// 双击项目：并行读取 settings.json UI 定义 + README，打开弹窗（两标签）
const openProjectSettings = async (proj: ProjectRow, index: number) => {
  if (!props.editable) return
  const folder = (proj.folderName || props.folderName || '').trim()
  settingsTab.value = 'config'
  settingsModal.projectIndex = index
  settingsModal.title = proj.name || folder || props.groupName
  settingsModal.open = true
  settingsModal.items = []
  settingsModal.readme = ''
  settingsModal.values = {
    ...((proj.jsScriptSettingsObject || {}) as Record<string, unknown>),
  }
  if (!folder) {
    settingsModal.loading = false
    return
  }
  settingsModal.loading = true
  try {
    const [uiResp, readmeResp] = await Promise.all([
      BetterGiService.getBettergiScriptSettingsUiApiApiScriptsBettergiScriptSettingsUiGet(
        props.scriptId,
        folder
      ),
      BetterGiService.getBettergiScriptReadmeApiApiScriptsBettergiScriptReadmeGet(
        props.scriptId,
        folder
      ),
    ])
    settingsModal.items = uiResp.code === 200 ? (uiResp.data || []) : []
    settingsModal.readme = readmeResp.code === 200 ? (readmeResp.data || '') : ''
    // 把 UI 定义里的 default 预置进本地值，避免保存时因缺项丢失默认设置
    for (const item of settingsModal.items) {
      const name = String(item?.name ?? '').trim()
      if (!name || item?.type === 'separator') continue
      if (settingsModal.values[name] === undefined && item?.default !== undefined) {
        settingsModal.values[name] = item.default
      }
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    settingsModal.items = []
    settingsModal.readme = ''
  } finally {
    settingsModal.loading = false
  }
}

const settingsTab = ref('config')

const fieldValue = (name: string): unknown => {
  const v = settingsModal.values[name]
  if (v === undefined) {
    // settings.json 定义里有 default 时兜底
    const def = settingsModal.items.find(i => i.name === name)?.default
    return def
  }
  return v
}

const fieldListValue = (name: string): string[] => {
  const v = fieldValue(name)
  if (Array.isArray(v)) return v.map(String)
  if (typeof v === 'string' && v.trim()) {
    // BetterGI multi-checkbox 可能以分隔符存字符串
    return v.split(/[;,；、]/).map(s => s.trim()).filter(Boolean)
  }
  return []
}

const setField = (name: string, value: unknown) => {
  settingsModal.values[name] = value
}

// 保存弹窗修改：js/pathing 无 json 载体时给出提示（保存按钮对非 scriptgroup 已禁用）
const saveProjectSettings = async () => {
  if (!isScriptGroup.value) {
    message.info(t('edit.bettergiProjectIndependentSaveLater'))
    return
  }
  const idx = settingsModal.projectIndex
  if (idx < 0 || idx >= projects.value.length) {
    settingsModal.open = false
    return
  }
  settingsModal.saving = true
  try {
    const list = projects.value.map((p, i) => (i === idx ? { ...p } : p))
    const target = list[idx]
    target.jsScriptSettingsObject = { ...settingsModal.values }
    projects.value = list
    await persistProjects()
    settingsModal.open = false
  } finally {
    settingsModal.saving = false
  }
}

// 初始化加载：props 变化（切换选中行）时重载
watch(
  () => `${props.kind}:${props.groupName}:${props.folderName}`,
  () => {
    settingsModal.open = false
    clearSelection()
    void reload()
  },
  { immediate: true }
)
defineExpose({ reload, addProjects, removeSelectedProjects })
</script>

<style scoped>
.bgi-project-editor {
  width: 100%;
}
.bgi-project-editor-disabled {
  opacity: 0.85;
}
/* 工具栏行 */
.bgi-project-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.bgi-project-toolbar-tip {
  margin-left: auto;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
  white-space: nowrap;
}
/* 多选提示条 */
.bgi-project-multi-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  margin-bottom: 8px;
  border: 1px dashed var(--ant-color-primary-border);
  border-radius: 6px;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
.bgi-project-list {
  max-height: 320px;
  overflow-y: auto;
  padding: 2px;
}
.bgi-project-sort-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bgi-project-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  cursor: default;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}
.bgi-project-row:hover {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg-hover);
}
.bgi-project-row-disabled {
  opacity: 0.7;
}
/* 选中（含 Shift/Ctrl 多选）行 */
.bgi-project-row-selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}
.bgi-project-row-selected:hover {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}
/* 拖拽热区：覆盖整行左侧 2/3（handle+名称+文件夹），仅最右勾选框在热区外 */
.bgi-project-drag-area {
  flex: 2 1 0%;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  cursor: grab;
}
/* JS/路径单项目行（无可选/多选）：热区占满整行 */
.bgi-project-drag-area-full {
  flex: 1 1 100%;
}
.bgi-project-drag-area:active {
  cursor: grabbing;
}
.bgi-project-drag-handle {
  flex: 0 0 auto;
  color: var(--ant-color-text-quaternary);
  font-size: 14px;
  transition: color 0.15s ease;
}
.bgi-project-drag-handle:hover {
  color: var(--ant-color-primary);
}
.bgi-project-drag-spacer {
  flex: 0 0 14px;
  height: 14px;
}
.bgi-project-name {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: var(--ant-color-text);
}
.bgi-project-folder {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
}
.bgi-project-row-state {
  flex: 1 1 0%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 24px;
}
.bgi-project-row-unselect {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 50%;
  line-height: 1;
  transition:
    background-color 0.15s ease,
    transform 0.1s ease;
}
.bgi-project-row-unselect:hover {
  background: rgba(0, 0, 0, 0.06);
  transform: scale(1.08);
}
.bgi-project-row-unselect:active {
  transform: scale(0.95);
}
.bgi-project-row-selected-icon {
  flex: 0 0 auto;
  color: var(--ant-color-primary);
  font-size: 15px;
}
.bgi-project-empty {
  padding: 12px 0;
}
.bgi-project-tip {
  margin: 10px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
  line-height: 1.6;
}
/* 拖拽中的行 */
.bgi-project-ghost {
  opacity: 0.35;
  background: var(--ant-color-primary-bg);
}
.bgi-project-chosen {
  border-color: var(--ant-color-primary);
}
.bgi-project-drag {
  cursor: grabbing;
}

/* 弹窗：标签页与字段 */
.bgi-project-settings-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 12px;
}
.bgi-project-settings-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 55vh;
  overflow-y: auto;
  padding: 4px 2px;
}
.bgi-project-separator {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
  border-top: 1px dashed var(--ant-color-border-secondary);
  padding-top: 8px;
  white-space: pre-line;
  line-height: 1.6;
}
.bgi-project-separator-first {
  border-top: none;
  padding-top: 0;
}
.bgi-project-setting-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: 12px;
  align-items: center;
}
.bgi-project-setting-label {
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-size: 14px;
  color: var(--ant-color-text);
  line-height: 1.6;
}
.bgi-project-setting-row :deep(.ant-select),
.bgi-project-setting-row :deep(.ant-input) {
  width: 100%;
}
.bgi-project-setting-row :deep(.ant-switch) {
  justify-self: start;
}
.bgi-project-settings-save-tip {
  margin: 10px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  text-align: right;
}
.bgi-project-settings-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100px;
  text-align: center;
  color: var(--ant-color-text-tertiary);
}
/* 脚本说明：保持换行与缩进 */
.bgi-project-readme {
  max-height: 55vh;
  overflow-y: auto;
  padding: 4px 2px;
}
.bgi-project-readme pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ant-color-text);
}
</style>
