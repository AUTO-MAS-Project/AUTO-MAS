<script setup lang="ts">
import { computed, ref, nextTick, reactive, onScopeDispose } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FolderOpenOutlined, GlobalOutlined, PlayCircleOutlined } from '@ant-design/icons-vue'
import BettergiAddChips from './BettergiAddChips.vue'
import BettergiAddSources from './BettergiAddSources.vue'
import {
  ONE_DRAGON_GROUPS,
  STAMINA_COMBAT_VISIBLE,
  STAMINA_COMBAT_KEY,
  type ConfigGroupIdentity,
} from './bettergiQueueIdentity'
import type { useBettergiCatalogs } from './useBettergiCatalogs'
const props = defineProps<{
  catalogs: ReturnType<typeof useBettergiCatalogs>
  locked: boolean
  editable: boolean
  customGroups: { name: string }[]
  groupLabel: (item: ConfigGroupIdentity) => string
  groupPrefix: (item: ConfigGroupIdentity) => string
  isGroupFrozen: (item: ConfigGroupIdentity) => boolean
  inDragon: (item: ConfigGroupIdentity) => boolean
  resolveStoredRowKind: (name: string) => ConfigGroupIdentity['kind']
  listCustomGroups: () => Promise<{ name: string }[]>
  addToQueue: (item: ConfigGroupIdentity) => boolean
  addProjects: (rows: unknown[]) => Promise<boolean>
}>()
const { groupLabel, groupPrefix, isGroupFrozen, inDragon, resolveStoredRowKind } = props
const {
  jsScriptOptions,
  scriptGroupOptions,
  keyMouseOptions,
  isJsScriptName,
  isKeyMouseName,
  isMasOwnGroup,
  jsDisplayName,
  pathingFileSet,
  loadJsScripts,
  loadScriptGroups,
  loadKeyMouseScripts,
  loadBettergiDirs,
  loadPathingTree,
  openBettergiScriptSite,
  openBettergiDir,
  openBettergiScheduler,
} = props.catalogs
const configLocked = computed(() => props.locked)
const groupsEditable = computed(() => props.editable)
const { t } = useI18n()
const logger = window.electronAPI.getLogger('BetterGI用户编辑')
let loadVersion = 0
onScopeDispose(() => {
  loadVersion += 1
})
const chipEditor = ref<InstanceType<typeof BettergiAddChips> | null>(null)
const sourcePicker = ref<InstanceType<typeof BettergiAddSources> | null>(null)
const clearChipSelection = () => chipEditor.value?.clearSelection()
const focusAddDraftInput = () => {
  void nextTick(() => chipEditor.value?.focus())
}
// ---- 添加弹窗（标签页：配置组/JS脚本/地图追踪）----
// 气泡列表元素：一条龙实例身份 + 弹窗内自增 uid（用于去重展示/删除，与队列行 uid 无关）
type AddChipItem = ConfigGroupIdentity & { chipUid: number }

const addModal = reactive({
  open: false,
  items: [] as AddChipItem[],
  draft: '',
  activeTab: 'scriptgroup' as 'scriptgroup' | 'js' | 'pathing' | 'keymouse',
  /** true=配置组编辑器内「添加脚本」：冻结「配置组」标签页，仅可从 JS脚本/地图追踪选择加入配置组 */
  addToGroupMode: false,
  /** JS脚本 标签页候选：自定义组 + JS 脚本（不含默认/专项/配置组，那些归「配置组」标签页） */
  candidates: [] as ConfigGroupIdentity[],
  /** 配置组 标签页候选：8 内置（默认）+ 体力作战（专项）+ ScriptGroup 目录内容 */
  groupCandidates: [] as ConfigGroupIdentity[],
  /** 录制 标签页候选：KeyMouseScript 目录下的键鼠脚本 */
  keyMouseCandidates: [] as ConfigGroupIdentity[],
})

// 添加弹窗标题/确定按钮文案（按模式分流）
const addModalTitle = computed<string>(() =>
  addModal.addToGroupMode
    ? t('core.edit.bettergiAddScriptToGroup')
    : t('core.edit.bettergiAddToDragon')
)

const addModalOkText = computed<string>(() =>
  addModal.addToGroupMode
    ? t('core.edit.bettergiAddScriptToGroupOk')
    : t('core.edit.bettergiAddToDragonOk')
)

const addModalOkButtonProps = computed(() => ({
  disabled: configLocked.value || (!addModal.items.length && !addModal.draft.trim()),
}))

// 弹窗气泡自增 uid 与行内输入焦点状态
let addChipSeq = 0

// 追加一个气泡（同一配置重复点击 → 生成独立实例气泡，对应重复添加语义）
const pushAddChip = (item: ConfigGroupIdentity) => {
  addModal.items.push({ ...item, chipUid: ++addChipSeq })
  focusAddDraftInput()
}

// 某候选是否已在气泡列表中（候选区 picked 高亮用）
const isChipAdded = (candidate: ConfigGroupIdentity): boolean =>
  addModal.items.some(c => c.kind === candidate.kind && c.key === candidate.key)

// BetterGI 现有自定义组名（仅作弹窗候选；打开弹窗不再合并进管理表，避免自动入队）
const bgiCustomCandidates = ref<string[]>([])

// 组装候选项，按标签页拆分：
//  - addModal.candidates（JS脚本 标签页）：JS 脚本 + 仅 custom 来源的现有自定义组
//  - addModal.groupCandidates（配置组 标签页）：8 内置（默认）+ 体力作战（专项）+ ScriptGroup 目录内容
// 现有自定义组若命中 ScriptGroup 目录（如「锄地一条龙」），在配置组标签页以 ScriptGroup 形式出现，
// 故 JS脚本 标签页剔除，避免同一配置两个入口。
const buildCandidates = () => {
  // 录制 标签页候选：KeyMouseScript 目录下的键鼠脚本（与其他标签页一样可加入队列）
  addModal.keyMouseCandidates = keyMouseOptions.value.map(opt => ({
    kind: 'keymouse' as const,
    key: opt.value,
  }))
  // addToGroupMode（配置组内添加脚本）只允许可执行的 JS 脚本目录与地图追踪路径；
  // 原有自定义组（custom）不写入配置组 projects，故 JS脚本 标签仅列 js 候选。
  if (addModal.addToGroupMode) {
    addModal.candidates = jsScriptOptions.value.map(opt => ({
      kind: 'js' as const,
      key: opt.value,
    }))
    addModal.groupCandidates = []
    return
  }
  const jsItems: ConfigGroupIdentity[] = []
  const jsTaken = new Set<string>()
  for (const row of props.customGroups) {
    const name = row.name
    // 现有自定义组按真实来源归类：仅「自定义组(custom)」入列 JS脚本 标签页；
    // 命中 JS脚本/路径/录制/ScriptGroup 目录的名字各有专属标签页，避免同一配置多处出现。
    const kind = resolveStoredRowKind(name)
    if (kind === 'custom' && !jsTaken.has(name)) {
      jsItems.push({ kind: 'custom', key: name })
      jsTaken.add(name)
    }
  }
  // BetterGI 现有、但尚未入管理表的自定义组仅作候选：用户显式确认才入队（不再打开即自动入队）
  for (const name of bgiCustomCandidates.value) {
    if (!jsTaken.has(name) && !props.customGroups.some(r => r.name === name)) {
      jsItems.push({ kind: 'custom', key: name })
      jsTaken.add(name)
    }
  }
  for (const opt of jsScriptOptions.value) {
    if (!jsTaken.has(opt.value)) {
      jsItems.push({ kind: 'js', key: opt.value })
      jsTaken.add(opt.value)
    }
  }
  addModal.candidates = jsItems

  const groupItems: ConfigGroupIdentity[] = []
  const groupTaken = new Set<string>()
  for (const g of ONE_DRAGON_GROUPS) {
    groupItems.push({ kind: 'builtin', key: g.value })
    groupTaken.add(g.value)
  }
  // 「体力作战」未开展制作时不出现在添加候选
  if (STAMINA_COMBAT_VISIBLE) {
    groupItems.push({ kind: 'stamina', key: STAMINA_COMBAT_KEY })
    groupTaken.add(STAMINA_COMBAT_KEY)
  }
  for (const opt of scriptGroupOptions.value) {
    if (groupTaken.has(opt.value)) continue
    // 「配置组」候选只应有三类：默认组、专项组、BGI User/ScriptGroup 里真实存在的配置组。
    // 后端为识别队列行会把该用户的 per-user 副本名一并返回，其中：
    //   1) 「脚本/录制」类自定义项的副本名与脚本目录名/录制名同名（OCRCountResin、
    //      提瓦特记事本DHXYHO…）——它们归属「脚本」「录制」标签页，不是配置组；
    //   2) MAS 自建组（MAS-{短id}-自定义配置组N / MAS-{短id}-执行层段N / MAS切换账号 /
    //      MAS一条龙）——运行期物化产物，用户不该在这里看到。
    // 二者在此剔除（2026-09-16 实机：添加自定义配置组后它们会冒进候选列表）。
    if (isMasOwnGroup(opt.value)) continue
    if (isJsScriptName(opt.value) || isKeyMouseName(opt.value)) continue
    groupItems.push({ kind: 'scriptgroup', key: opt.value })
    groupTaken.add(opt.value)
  }
  addModal.groupCandidates = groupItems
}

// 普通「添加配置组到一条龙」弹窗
const openAddToDragonModal = async () => {
  addModal.addToGroupMode = false
  await openAddModalCommon('scriptgroup')
}

// 配置组编辑器「添加脚本」：复用同一弹窗但冻结「配置组」标签，只可加 JS 脚本/地图追踪/录制到配置组。
// 适用 scriptgroup / 录制(keymouse) / 脚本(js) / 路径(pathing) 四类：后两者以 per-user ScriptGroup 副本充当配置组。
const openAddScriptToGroup = async () => {
  if (!props.editable) return
  addModal.addToGroupMode = true
  await openAddModalCommon('js')
}

const openAddModalCommon = async (defaultTab: 'scriptgroup' | 'js' | 'pathing' | 'keymouse') => {
  const version = ++loadVersion
  const current = () => version === loadVersion && addModal.open
  addModal.items = []
  addModal.draft = ''
  addModal.activeTab = defaultTab
  sourcePicker.value?.resetAnchors()
  clearChipSelection()
  addModal.open = true
  // 仅读取 BetterGI 现有自定义组作为弹窗候选；不再合并进管理表，避免打开弹窗即自动入队
  const bgiGroups = await props.listCustomGroups()
  if (!current()) return
  bgiCustomCandidates.value = bgiGroups
    .map(r => r.name)
    .filter(n => resolveStoredRowKind(n) === 'custom')
  await Promise.all([
    loadJsScripts(),
    loadScriptGroups(),
    loadKeyMouseScripts(),
    loadBettergiDirs(),
    loadPathingTree(),
  ])
  if (!current()) return
  buildCandidates()
}

// 关闭弹窗（两模式共用）
const cancelAddModal = () => {
  loadVersion += 1
  addModal.addToGroupMode = false
  clearChipSelection()
  addModal.open = false
}

// 把选中项转成 ScriptGroup json 的 project 行（js=目录名+manifest 名；pathing=相对路径文件夹/文件名）
const toScriptGroupProjectRow = (item: AddChipItem): Record<string, unknown> | null => {
  if (item.kind === 'js') {
    const folder = item.key
    if (!folder) return null
    return {
      name: jsDisplayName(folder),
      folderName: folder,
      index: 0,
      type: 'Javascript',
      status: 'Enabled',
      schedule: 'Daily',
      runNum: 1,
      allowJsNotification: true,
      allowJsHTTPHash: '',
      jsScriptSettingsObject: {},
    }
  }
  if (item.kind === 'keymouse') {
    const rec = String(item.key || '').trim()
    if (!rec) return null
    return {
      name: rec,
      folderName: rec,
      index: 0,
      type: 'KeyMouse',
      status: 'Enabled',
      schedule: 'Daily',
      runNum: 1,
      allowJsNotification: true,
      allowJsHTTPHash: '',
    }
  }
  if (item.kind === 'pathing') {
    const rel = String(item.key || '').trim()
    if (!rel) return null
    const segments = rel.split('/')
    const file = segments.pop() || rel
    const folder = segments.join('/')
    return {
      name: `${file}.json`,
      folderName: folder,
      index: 0,
      type: 'Pathing',
      status: 'Enabled',
      schedule: 'Daily',
      runNum: 1,
    }
  }
  return null
}

// 候选点击：直接生成一个气泡（同配置重复点击=多个独立实例）
const pickAddCandidate = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  pushAddChip(item)
}

// 按名称在候选中定位配置组（内置按 value/翻译名，自定义按组名，体力作战按展示名）。
// JS脚本 与 配置组 两个标签页的候选都参与识别，保证行内手动输入也能命中。
// 配置组模式（添加脚本到配置组）下只允许 JS 脚本目录，故仅查 addModal.candidates。
const findCandidateByName = (name: string): ConfigGroupIdentity | undefined => {
  const list = addModal.addToGroupMode
    ? addModal.candidates
    : [...addModal.candidates, ...addModal.groupCandidates]
  return list.find(c => c.key === name || groupLabel(c) === name)
}

// 输入段解析：候选优先，命中 AutoPathing 相对路径（pathingFileSet）则按「路径」加入
const resolveInputName = (name: string): ConfigGroupIdentity | undefined => {
  const candidate = findCandidateByName(name)
  if (candidate) return candidate
  if (pathingFileSet.value.has(name)) return { kind: 'pathing', key: name }
  return undefined
}

// 拆分行内输入内容：支持「;」「；」分隔，返回去空白的组名字面量列表
const splitGroupNames = (raw: string): string[] =>
  (raw || '')
    .split(/[;；]/)
    .map(s => s.trim())
    .filter(Boolean)

// 提交行内草稿：每段必须全部可识别才生成气泡；有未知段则阻止并提示（拼写检查）
const commitAddDraft = (): boolean => {
  const names = splitGroupNames(addModal.draft)
  if (!names.length) return true
  const unknown = names.filter(n => !resolveInputName(n))
  if (unknown.length) {
    message.warning(t('core.edit.bettergiGroupNamesUnknown', { names: unknown.join('、') }))
    return false
  }
  for (const n of names) {
    const target = resolveInputName(n)
    if (target) pushAddChip(target)
  }
  addModal.draft = ''
  return true
}

// 确认：加入一条龙 或（配置组模式）作为项目写入当前配置组 json
const confirmAddToDragon = async () => {
  if (configLocked.value) {
    message.error(t('core.edit.configLocked'))
    return
  }
  if (addModal.draft.trim() && !commitAddDraft()) return
  if (!addModal.items.length) {
    message.warning(t('core.edit.bettergiPickCandidateFirst'))
    return
  }
  const items = [...addModal.items]
  // 配置组模式：把 JS/路径转成 project 行，交给右栏编辑器追加并保存
  if (addModal.addToGroupMode) {
    const rows = items
      .map(toScriptGroupProjectRow)
      .filter((r): r is Record<string, unknown> => r !== null)
    if (!rows.length) {
      addModal.items = []
      addModal.draft = ''
      clearChipSelection()
      addModal.addToGroupMode = false
      addModal.open = false
      message.warning(t('core.edit.bettergiAddScriptUnsupported'))
      return
    }
    try {
      const added = await props.addProjects(rows)
      if (!added) return
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('core.edit.bettergiProjectSaveFailed'))
      return
    }
    addModal.items = []
    addModal.draft = ''
    clearChipSelection()
    addModal.addToGroupMode = false
    addModal.open = false
    return
  }
  for (const item of items) {
    if (!props.addToQueue({ kind: item.kind, key: item.key })) return
  }
  addModal.items = []
  addModal.draft = ''
  clearChipSelection()
  addModal.open = false
}
defineExpose({ open: openAddToDragonModal, openForGroup: openAddScriptToGroup })
</script>
<template>
  <a-modal
    v-model:open="addModal.open"
    :title="addModalTitle"
    :ok-text="addModalOkText"
    :ok-button-props="addModalOkButtonProps"
    :cancel-text="t('core.edit.cancel')"
    width="920px"
    :z-index="1200"
    class="add-dragon-modal"
    @ok="confirmAddToDragon"
    @cancel="cancelAddModal"
  >
    <!-- 顶部：标签输入（彩色气泡 + 行内输入） + 打开目录按钮 -->
    <div class="add-dragon-input-row">
      <BettergiAddChips
        ref="chipEditor"
        v-model:items="addModal.items"
        v-model:draft="addModal.draft"
        :group-label="groupLabel"
        @commit="commitAddDraft"
      />
      <div class="add-dragon-dir-buttons">
        <a-space direction="vertical" size="small" class="add-dragon-dir-col">
          <a-space size="small">
            <a-button size="small" @click="openBettergiScriptSite">
              <template #icon><GlobalOutlined /></template>
              {{ t('core.edit.bettergiOpenScriptRepo') }}
            </a-button>
            <a-button size="small" @click="openBettergiDir('jsScript')">
              <template #icon><FolderOpenOutlined /></template>
              {{ t('core.edit.bettergiOpenScriptDir') }}
            </a-button>
            <a-button size="small" @click="openBettergiDir('autoPathing')">
              <template #icon><FolderOpenOutlined /></template>
              {{ t('core.edit.bettergiOpenTaskDir') }}
            </a-button>
          </a-space>
          <a-space size="small">
            <a-button size="small" @click="openBettergiScheduler">
              <template #icon><PlayCircleOutlined /></template>
              {{ t('core.edit.bettergiOpenBgi') }}
            </a-button>
            <a-button size="small" @click="openBettergiDir('keyMouse')">
              <template #icon><FolderOpenOutlined /></template>
              {{ t('core.edit.bettergiOpenKeyMouseDir') }}
            </a-button>
            <a-button size="small" @click="openBettergiDir('scriptGroup')">
              <template #icon><FolderOpenOutlined /></template>
              {{ t('core.edit.bettergiOpenScriptGroupDir') }}
            </a-button>
          </a-space>
        </a-space>
      </div>
    </div>
    <p class="add-dragon-input-tip">{{ t('core.edit.bettergiInputGroupNamesTip') }}</p>

    <BettergiAddSources
      ref="sourcePicker"
      v-model:active-tab="addModal.activeTab"
      :catalogs="props.catalogs"
      :editable="props.editable"
      :group-mode="addModal.addToGroupMode"
      :candidates="addModal.candidates"
      :group-candidates="addModal.groupCandidates"
      :key-mouse-candidates="addModal.keyMouseCandidates"
      :group-label="groupLabel"
      :group-prefix="groupPrefix"
      :is-group-frozen="isGroupFrozen"
      :in-dragon="inDragon"
      :is-chip-added="isChipAdded"
      @pick="pickAddCandidate"
    />
  </a-modal>
</template>
<style scoped>
.add-dragon-modal :deep(.ant-modal-body) {
  max-height: 70vh;
  overflow-y: auto;
}

.add-dragon-input-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.add-dragon-input-row .add-dragon-input {
  flex: 1 1 auto;
  margin-bottom: 0;
}

.add-dragon-dir-buttons {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.add-dragon-dir-buttons .ant-space {
  flex-wrap: wrap;
}

.add-dragon-input {
  margin-bottom: 8px;
}

.add-dragon-input-tip {
  margin: 8px 0 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}
</style>
