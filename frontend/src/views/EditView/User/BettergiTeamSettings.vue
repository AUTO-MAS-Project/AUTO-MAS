<template>
  <div class="team-config-section">
    <div class="section-header">
      <h3>
        {{ t('edit.bettergiTeamConfig') }}
        <a-tooltip :title="t('edit.bettergiTeamConfigHint')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
        <div class="team-master-capsule" :class="{ active: teamsOn }" @click="toggleMaster">
          <span class="team-master-dot"></span>
        </div>
      </h3>
    </div>

    <a-alert v-if="!editable" type="info" show-icon class="mode-guide-alert">
      <template #message>
        <span class="mode-guide-message">{{ t('edit.bettergiDirectModeAlert') }}</span>
      </template>
    </a-alert>

    <p v-if="!teamsOn" class="team-off-tip">{{ t('edit.bettergiTeamOffTip') }}</p>

    <template v-else>
      <div class="team-toolbar">
        <a-space size="small" wrap>
          <a-button size="small" type="primary" :disabled="!canEdit" @click="openEdit()">
            <template #icon><PlusOutlined /></template>
            {{ t('edit.bettergiTeamAdd') }}
          </a-button>
          <a-button
            size="small"
            danger
            :disabled="!canEdit || !selectedUids.length"
            @click="deleteSelected"
          >
            <template #icon><DeleteOutlined /></template>
            {{ t('edit.bettergiTeamBatchDelete') }}
          </a-button>
          <a-button size="small" @click="emit('open-strategy-dir')">
            <template #icon><FolderOpenOutlined /></template>
            {{ t('edit.bettergiTeamOpenStrategyDir') }}
          </a-button>
          <a-button size="small" disabled>
            {{ t('edit.bettergiTeamAdvanced') }}
          </a-button>
        </a-space>
        <span class="team-toolbar-tip">{{ t('edit.bettergiTeamDragTip') }}</span>
      </div>

      <div class="team-table">
        <div class="team-table-head">
          <span class="team-cell team-cell-check"></span>
          <span class="team-cell team-cell-index">{{ t('edit.bettergiTeamIndexColumn') }}</span>
          <span class="team-cell team-cell-name">{{ t('edit.bettergiTeamNameColumn') }}</span>
          <span class="team-cell team-cell-strategy">{{
            t('edit.bettergiTeamStrategyColumn')
          }}</span>
          <span class="team-cell team-cell-scenes">{{ t('edit.bettergiTeamScenesColumn') }}</span>
          <span class="team-cell team-cell-note">{{ t('edit.bettergiTeamNoteColumn') }}</span>
          <span class="team-cell team-cell-actions">{{ t('edit.bettergiTeamActionColumn') }}</span>
        </div>

        <!-- 通用队伍：固定首位、不可拖拽、不可删除；名称与策略直绑任务配置字段（双向同步） -->
        <div class="team-row team-row-general">
          <span class="team-cell team-cell-check">
            <a-tag size="small" color="blue">{{ t('edit.bettergiTeamGeneralTag') }}</a-tag>
          </span>
          <span class="team-cell team-cell-index">0</span>
          <span class="team-cell team-cell-name">
            <a-input
              :value="generalName"
              size="small"
              :disabled="!editable"
              :placeholder="t('edit.bettergiEnterBattleParty')"
              @update:value="(v: string) => saveGeneral('OneDragon.PartyName', v)"
            />
          </span>
          <span class="team-cell team-cell-strategy">
            <a-select
              :value="generalStrategy"
              size="small"
              style="width: 100%"
              allow-clear
              show-search
              :disabled="!editable"
              :placeholder="t('edit.bettergiTeamStrategyFollowGeneral')"
              :options="strategyOptions"
              @update:value="
                (v: string | undefined) => saveGeneral('OneDragon.AutoBossStrategyName', v ?? '')
              "
            />
          </span>
          <span class="team-cell team-cell-scenes">
            <a-tag size="small">{{ t('edit.bettergiTeamGeneralScene') }}</a-tag>
          </span>
          <span class="team-cell team-cell-note">—</span>
          <span class="team-cell team-cell-actions">
            <span class="team-row-hint">{{ t('edit.bettergiTeamGeneralHint') }}</span>
          </span>
        </div>

        <draggable v-model="rows" item-key="uid" handle=".team-drag-handle" :disabled="!canEdit">
          <template #item="{ element }">
            <div class="team-row">
              <span class="team-cell team-cell-check">
                <a-checkbox
                  :checked="selectedUids.includes(element.uid)"
                  :disabled="!canEdit"
                  @change="toggleSelect(element.uid)"
                />
              </span>
              <span class="team-cell team-cell-index">
                <span class="team-drag-handle" :class="{ disabled: !canEdit }">
                  <MenuOutlined />
                </span>
                {{ rows.indexOf(element) + 1 }}
              </span>
              <span class="team-cell team-cell-name">{{ element.name }}</span>
              <span class="team-cell team-cell-strategy">
                <span v-if="element.strategy">{{ element.strategy }}</span>
                <span v-else class="team-muted">{{
                  t('edit.bettergiTeamStrategyFollowGeneral')
                }}</span>
              </span>
              <span class="team-cell team-cell-scenes">
                <template v-if="sceneTags(element).length">
                  <a-tag v-for="tag in sceneTags(element)" :key="tag" size="small">{{ tag }}</a-tag>
                </template>
                <span v-else class="team-muted">{{ t('edit.bettergiTeamNoScene') }}</span>
                <a-button
                  type="link"
                  size="small"
                  :disabled="!canEdit"
                  @click="openScenesForRow(element)"
                >
                  {{ t('edit.bettergiTeamEditScenes') }}
                </a-button>
              </span>
              <span class="team-cell team-cell-note">{{ element.note || '—' }}</span>
              <span class="team-cell team-cell-actions">
                <a-button
                  class="team-row-action-btn"
                  type="text"
                  size="small"
                  :disabled="!canEdit"
                  :aria-label="t('edit.bettergiTeamEdit')"
                  @click="openEdit(element)"
                >
                  <template #icon><EditOutlined /></template>
                </a-button>
                <a-button
                  class="team-row-action-btn"
                  type="text"
                  size="small"
                  :disabled="!canEdit"
                  :aria-label="t('edit.bettergiTeamDuplicate')"
                  @click="duplicateRow(element)"
                >
                  <template #icon><CopyOutlined /></template>
                </a-button>
                <a-button
                  class="team-row-action-btn"
                  type="text"
                  size="small"
                  danger
                  :disabled="!canEdit"
                  :aria-label="t('edit.bettergiTeamDelete')"
                  @click="removeRow(element)"
                >
                  <template #icon><DeleteOutlined /></template>
                </a-button>
                <div
                  class="team-enable-capsule"
                  :class="{ active: element.enabled, disabled: !canEdit }"
                  @click="canEdit && toggleEnabled(element)"
                >
                  <span class="team-enable-dot"></span>
                </div>
              </span>
            </div>
          </template>
        </draggable>

        <a-empty v-if="!rows.length" :description="t('edit.bettergiTeamEmpty')" />
      </div>
    </template>

    <!-- 添加 / 编辑队伍弹窗（备注为最后一栏） -->
    <a-modal
      v-model:open="editModal.open"
      :title="editModal.index == null ? t('edit.bettergiTeamAdd') : t('edit.bettergiTeamEditTitle')"
      :confirm-loading="editModal.saving"
      @ok="confirmEdit"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('edit.bettergiTeamNameColumn')" required>
          <a-input
            v-model:value="editModal.draft.name"
            :placeholder="t('edit.bettergiEnterBattleParty')"
            :maxlength="60"
          />
        </a-form-item>
        <a-form-item :label="t('edit.bettergiTeamStrategyColumn')">
          <a-select
            v-model:value="editModal.draft.strategy"
            allow-clear
            show-search
            :placeholder="t('edit.bettergiTeamStrategyFollowGeneral')"
            :options="strategyOptions"
          />
          <p class="team-field-tip">{{ t('edit.bettergiTeamStrategyTip') }}</p>
        </a-form-item>
        <a-form-item :label="t('edit.bettergiTeamScenesColumn')">
          <a-space size="small" wrap>
            <a-tag v-for="tag in sceneTags(editModal.draft)" :key="tag" size="small">{{
              tag
            }}</a-tag>
            <span v-if="!sceneTags(editModal.draft).length" class="team-muted">
              {{ t('edit.bettergiTeamNoScene') }}
            </span>
          </a-space>
          <div>
            <a-button size="small" type="dashed" @click="openScenesForDraft">
              <template #icon><PlusOutlined /></template>
              {{ t('edit.bettergiTeamEditScenes') }}
            </a-button>
          </div>
          <p class="team-field-tip">{{ t('edit.bettergiTeamSceneTip') }}</p>
        </a-form-item>
        <a-form-item :label="t('edit.bettergiTeamNoteColumn')">
          <a-textarea v-model:value="editModal.draft.note" :rows="2" :maxlength="200" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 战斗场景弹窗：三个标签页，条件可跨标签页任意叠加 -->
    <a-modal
      v-model:open="sceneModal.open"
      :title="t('edit.bettergiTeamScenesColumn')"
      width="820px"
      @ok="confirmScenes"
    >
      <a-tabs v-model:activeKey="sceneModal.tab">
        <a-tab-pane key="domain" :tab="t('edit.bettergiTeamSceneDomainTab')">
          <div v-for="(cond, i) in editModal.draft.scenes.domain" :key="`d${i}`" class="scene-cond">
            <a-select
              :value="cond.region || undefined"
              style="width: 130px"
              allow-clear
              :placeholder="t('edit.bettergiTeamSceneRegion')"
              :options="domainRegionOptions"
              @update:value="(v: string | undefined) => onDomainRegion(cond, v)"
            />
            <a-select
              :value="cond.domain || undefined"
              style="width: 210px"
              show-search
              :placeholder="t('edit.bettergiTeamSceneDomain')"
              :options="domainNameOptions(cond.region)"
              @update:value="(v: string | undefined) => onDomainName(cond, v)"
            />
            <a-select
              :value="cond.reward || undefined"
              style="width: 200px"
              allow-clear
              :placeholder="t('edit.bettergiTeamSceneReward')"
              :options="domainRewardOptions(cond.domain)"
              @update:value="(v: string | undefined) => (cond.reward = v ?? '')"
            />
            <a-button type="text" size="small" danger @click="removeCond('domain', i)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
          <a-button size="small" type="dashed" block @click="addCond('domain')">
            <template #icon><PlusOutlined /></template>
            {{ t('edit.bettergiTeamSceneAddDomain') }}
          </a-button>
        </a-tab-pane>

        <a-tab-pane key="leyline" :tab="t('edit.bettergiTeamSceneLeylineTab')">
          <div
            v-for="(cond, i) in editModal.draft.scenes.leyline"
            :key="`l${i}`"
            class="scene-cond"
          >
            <a-select
              :value="cond.country || undefined"
              style="width: 150px"
              :placeholder="t('edit.bettergiTeamSceneCountry')"
              :options="leylineCountryOptions"
              @update:value="(v: string) => (cond.country = v)"
            />
            <a-select
              :value="cond.type || undefined"
              style="width: 240px"
              :placeholder="t('edit.bettergiTeamSceneLeylineType')"
              :options="leylineTypeOptions"
              @update:value="(v: string) => (cond.type = v)"
            />
            <a-button type="text" size="small" danger @click="removeCond('leyline', i)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
          <a-button size="small" type="dashed" block @click="addCond('leyline')">
            <template #icon><PlusOutlined /></template>
            {{ t('edit.bettergiTeamSceneAddLeyline') }}
          </a-button>
        </a-tab-pane>

        <a-tab-pane key="boss" :tab="t('edit.bettergiTeamSceneBossTab')">
          <div v-for="(cond, i) in editModal.draft.scenes.boss" :key="`b${i}`" class="scene-cond">
            <a-select
              :value="cond.region || undefined"
              style="width: 130px"
              allow-clear
              :placeholder="t('edit.bettergiTeamSceneRegion')"
              :options="bossRegionOptions"
              @update:value="(v: string | undefined) => onBossRegion(cond, v)"
            />
            <a-select
              :value="cond.boss || undefined"
              style="width: 240px"
              show-search
              :placeholder="t('edit.bettergiTeamSceneBoss')"
              :options="bossOptions(cond.region)"
              @update:value="(v: string) => (cond.boss = v)"
            />
            <a-button type="text" size="small" danger @click="removeCond('boss', i)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
          <a-button size="small" type="dashed" block @click="addCond('boss')">
            <template #icon><PlusOutlined /></template>
            {{ t('edit.bettergiTeamSceneAddBoss') }}
          </a-button>
        </a-tab-pane>
      </a-tabs>
      <p class="team-field-tip">{{ t('edit.bettergiTeamSceneDialogTip') }}</p>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  FolderOpenOutlined,
  MenuOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'

type SceneKey = 'domain' | 'leyline' | 'boss'
type SceneCond = Record<string, string>
type Scenes = Record<SceneKey, SceneCond[]>

interface TeamRow {
  uid: number
  name: string
  strategy: string
  scenes: Scenes
  note: string
  enabled: boolean
}

interface SelectOption {
  label: string
  value: string
}

const props = defineProps<{
  formData: Record<string, any>
  editable: boolean
  strategyOptions: SelectOption[]
  domainCatalog: Array<{ name: string; region?: string; rewards?: string[] }>
  bossCatalog: Array<{ region: string; name: string; label: string }>
  leylineCountryOptions: SelectOption[]
  leylineTypeOptions: SelectOption[]
}>()

const emit = defineEmits<{
  (e: 'save', key: string, value: unknown): void
  (e: 'open-strategy-dir'): void
}>()

const { t } = useI18n()

// ---- 基础状态 ----
const rows = ref<TeamRow[]>([])
const selectedUids = ref<number[]>([])
let uidSeq = 0
// 自身写回引起的 watch 触发需跳过重建，否则拖拽/多选状态每次落库都被重置
let selfWriting = false

const oneDragon = computed<Record<string, any>>(() => props.formData?.OneDragon ?? {})
const teamsOn = computed<boolean>(() => !!oneDragon.value.IfUseTeams)
const canEdit = computed<boolean>(() => props.editable && teamsOn.value)
const generalName = computed<string>(() => String(oneDragon.value.PartyName ?? ''))
const generalStrategy = computed<string>(() => String(oneDragon.value.AutoBossStrategyName ?? ''))

const emptyScenes = (): Scenes => ({ domain: [], leyline: [], boss: [] })

const normalizeScenes = (raw: unknown): Scenes => {
  const src = (raw ?? {}) as Record<string, unknown>
  const pick = (key: SceneKey): SceneCond[] =>
    Array.isArray(src[key])
      ? (src[key] as unknown[])
          .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
          .map(x => {
            const out: SceneCond = {}
            for (const [k, v] of Object.entries(x)) if (v != null) out[k] = String(v)
            return out
          })
      : []
  return { domain: pick('domain'), leyline: pick('leyline'), boss: pick('boss') }
}

const parseTeams = (raw: unknown): Omit<TeamRow, 'uid'>[] => {
  let arr: unknown = raw
  if (typeof raw === 'string') {
    if (!raw.trim()) return []
    try {
      arr = JSON.parse(raw)
    } catch {
      return []
    }
  }
  if (!Array.isArray(arr)) return []
  return arr
    .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object' && !!x.name)
    .map(x => ({
      name: String(x.name),
      strategy: String(x.strategy ?? ''),
      scenes: normalizeScenes(x.scenes),
      note: String(x.note ?? ''),
      enabled: x.enabled !== false,
    }))
}

/** 落库：只序列化业务字段（uid 为纯前端行标识，不进配置） */
const persist = () => {
  const payload = rows.value.map(r => ({
    name: r.name,
    strategy: r.strategy,
    scenes: r.scenes,
    note: r.note,
    enabled: r.enabled,
  }))
  const str = JSON.stringify(payload)
  selfWriting = true
  oneDragon.value.Teams = str
  emit('save', 'OneDragon.Teams', str)
  void nextTick(() => {
    selfWriting = false
  })
}

const syncFromForm = () => {
  rows.value = parseTeams(oneDragon.value.Teams).map(r => ({ ...r, uid: ++uidSeq }))
  selectedUids.value = []
}

watch(
  () => oneDragon.value.Teams,
  () => {
    if (selfWriting) return
    syncFromForm()
  },
  { immediate: true }
)

// ---- 总开关 ----
const toggleMaster = () => {
  if (!props.editable) return
  const next = !oneDragon.value.IfUseTeams
  oneDragon.value.IfUseTeams = next
  emit('save', 'OneDragon.IfUseTeams', next)
}

/** 通用队伍：直接读写任务配置字段（与任务配置卡片互通，改一处两处同步） */
const saveGeneral = (
  key: 'OneDragon.PartyName' | 'OneDragon.AutoBossStrategyName',
  value: string
) => {
  const field = key === 'OneDragon.PartyName' ? 'PartyName' : 'AutoBossStrategyName'
  oneDragon.value[field] = value
  emit('save', key, value)
}

// ---- 表格选择与行操作 ----
const toggleSelect = (uid: number) => {
  selectedUids.value = selectedUids.value.includes(uid)
    ? selectedUids.value.filter(x => x !== uid)
    : [...selectedUids.value, uid]
}

const deleteSelected = () => {
  if (!selectedUids.value.length) return
  const removed = new Set(selectedUids.value)
  rows.value = rows.value.filter(r => !removed.has(r.uid))
  selectedUids.value = []
  persist()
}

const toggleEnabled = (row: TeamRow) => {
  row.enabled = !row.enabled
  persist()
}

const removeRow = (row: TeamRow) => {
  rows.value = rows.value.filter(r => r.uid !== row.uid)
  selectedUids.value = selectedUids.value.filter(x => x !== row.uid)
  persist()
}

/** 复制：继承原行启用状态（含顺序，插在源行之后） */
const duplicateRow = (row: TeamRow) => {
  const copy: TeamRow = {
    uid: ++uidSeq,
    name: row.name,
    strategy: row.strategy,
    scenes: JSON.parse(JSON.stringify(row.scenes)) as Scenes,
    note: row.note,
    enabled: row.enabled,
  }
  const index = rows.value.findIndex(r => r.uid === row.uid)
  rows.value.splice(index + 1, 0, copy)
  persist()
}

// ---- 编辑弹窗 ----
const editModal = reactive({
  open: false,
  saving: false,
  index: null as number | null,
  draft: {
    name: '',
    strategy: '',
    scenes: emptyScenes(),
    note: '',
  } as Omit<TeamRow, 'uid' | 'enabled'>,
})

const openEdit = (row?: TeamRow) => {
  editModal.index = row ? rows.value.findIndex(r => r.uid === row.uid) : null
  editModal.draft = row
    ? {
        name: row.name,
        strategy: row.strategy,
        scenes: JSON.parse(JSON.stringify(row.scenes)) as Scenes,
        note: row.note,
      }
    : { name: '', strategy: '', scenes: emptyScenes(), note: '' }
  editModal.open = true
}

const confirmEdit = () => {
  const name = editModal.draft.name.trim()
  if (!name) {
    message.warning(t('edit.bettergiTeamNameRequired'))
    return
  }
  if (rows.value.some((r, i) => r.name === name && i !== editModal.index)) {
    message.warning(t('edit.bettergiTeamNameExists'))
    return
  }
  editModal.saving = true
  try {
    const scenes = pruneScenes(editModal.draft.scenes)
    if (editModal.index == null) {
      rows.value.push({
        uid: ++uidSeq,
        name,
        strategy: editModal.draft.strategy,
        scenes,
        note: editModal.draft.note,
        enabled: true,
      })
    } else {
      const target = rows.value[editModal.index]
      if (target) {
        target.name = name
        target.strategy = editModal.draft.strategy
        target.scenes = scenes
        target.note = editModal.draft.note
      }
    }
    persist()
    editModal.open = false
  } finally {
    editModal.saving = false
  }
}

// ---- 战斗场景弹窗 ----
const sceneModal = reactive({
  open: false,
  tab: 'domain' as SceneKey,
  targetUid: null as number | null,
  fromEdit: false,
})

const openScenesForDraft = () => {
  sceneModal.fromEdit = true
  sceneModal.targetUid = null
  sceneModal.open = true
}

/** 表格「战斗场景」单元格直接进入：不打开编辑弹窗，确认后立即落库 */
const openScenesForRow = (row: TeamRow) => {
  editModal.index = rows.value.findIndex(r => r.uid === row.uid)
  editModal.draft = {
    name: row.name,
    strategy: row.strategy,
    scenes: JSON.parse(JSON.stringify(row.scenes)) as Scenes,
    note: row.note,
  }
  sceneModal.fromEdit = false
  sceneModal.targetUid = row.uid
  sceneModal.open = true
}

/** 只保留填了关键字段的条件，避免空行落库后误命中（奖励档仅展示，非必填） */
const pruneScenes = (scenes: Scenes): Scenes => ({
  domain: scenes.domain.filter(c => (c.domain ?? '').trim()),
  leyline: scenes.leyline.filter(c => (c.country ?? '').trim() && (c.type ?? '').trim()),
  boss: scenes.boss.filter(c => (c.boss ?? '').trim()),
})

const confirmScenes = () => {
  const scenes = pruneScenes(editModal.draft.scenes)
  editModal.draft.scenes = scenes
  if (!sceneModal.fromEdit && sceneModal.targetUid != null) {
    const target = rows.value.find(r => r.uid === sceneModal.targetUid)
    if (target) {
      target.scenes = scenes
      persist()
    }
  }
  sceneModal.open = false
}

const addCond = (key: SceneKey) => {
  editModal.draft.scenes[key].push(
    key === 'leyline'
      ? { country: '', type: '' }
      : key === 'boss'
        ? { region: '', boss: '' }
        : { region: '', domain: '', reward: '' }
  )
}

const removeCond = (key: SceneKey, index: number) => {
  editModal.draft.scenes[key].splice(index, 1)
}

// ---- 选项来源（复用后端秘境目录 / 首领目录 / 地脉常量） ----
const domainRegionOptions = computed<SelectOption[]>(() => {
  const regions = new Set<string>()
  for (const item of props.domainCatalog) if (item.region) regions.add(item.region)
  return Array.from(regions).map(region => ({ label: region, value: region }))
})

const bossRegionOptions = computed<SelectOption[]>(() => {
  const regions = new Set<string>()
  for (const item of props.bossCatalog) if (item.region) regions.add(item.region)
  return Array.from(regions).map(region => ({ label: region, value: region }))
})

const domainNameOptions = (region?: string): SelectOption[] =>
  props.domainCatalog
    .filter(d => !region || d.region === region)
    .map(d => ({ label: d.name, value: d.name }))

const bossOptions = (region?: string): SelectOption[] =>
  props.bossCatalog
    .filter(b => !region || b.region === region)
    .map(b => ({ label: b.label, value: b.name }))

const domainRewardOptions = (domainName?: string): SelectOption[] => {
  const item = props.domainCatalog.find(d => d.name === domainName)
  return (item?.rewards ?? []).map((r, idx) => ({ label: r, value: String(idx + 1) }))
}

/** 改地区后原秘境不在新地区内则一并清空，避免留下不一致的条件 */
const onDomainRegion = (cond: SceneCond, region?: string) => {
  cond.region = region ?? ''
  if (cond.domain && !domainNameOptions(cond.region).some(o => o.value === cond.domain)) {
    cond.domain = ''
    cond.reward = ''
  }
}

const onDomainName = (cond: SceneCond, name?: string) => {
  cond.domain = name ?? ''
  cond.reward = ''
}

const onBossRegion = (cond: SceneCond, region?: string) => {
  cond.region = region ?? ''
  if (cond.boss && !bossOptions(cond.region).some(o => o.value === cond.boss)) {
    cond.boss = ''
  }
}

/** 场景摘要标签：秘境显示秘境名，地脉显示「地区-类型」，首领显示「首领-地区」 */
const sceneTags = (row: { scenes: Scenes }): string[] => {
  const tags: string[] = []
  for (const c of row.scenes.domain) if (c.domain) tags.push(c.domain)
  for (const c of row.scenes.leyline)
    if (c.type) tags.push(c.country ? `${c.country}-${c.type}` : c.type)
  for (const c of row.scenes.boss) {
    if (!c.boss) continue
    const label = props.bossCatalog.find(b => b.name === c.boss)?.label
    tags.push(label ?? c.boss)
  }
  return tags
}

defineExpose({ syncFromForm })
</script>

<style scoped>
.team-master-capsule {
  display: inline-flex;
  align-items: center;
  width: 40px;
  height: 20px;
  margin-left: 10px;
  padding: 0 2px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.18);
  cursor: pointer;
  transition: background 0.2s ease;
  vertical-align: middle;
}

.team-master-capsule.active {
  background: var(--ant-color-primary, #1677ff);
}

.team-master-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s ease;
}

.team-master-capsule.active .team-master-dot {
  transform: translateX(20px);
}

.team-off-tip {
  margin: 8px 0 0;
  color: rgba(0, 0, 0, 0.45);
}

.team-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.team-toolbar-tip {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.team-table {
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 8px;
  overflow: hidden;
}

.team-table-head,
.team-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
}

.team-table-head {
  background: rgba(0, 0, 0, 0.02);
  font-weight: 600;
  font-size: 12px;
}

.team-row + .team-row,
.team-table-head + .team-row {
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.team-row-general {
  background: rgba(22, 119, 255, 0.04);
}

.team-cell {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.team-cell-check {
  width: 60px;
  flex: none;
}

.team-cell-index {
  width: 70px;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.team-cell-name {
  width: 190px;
  flex: none;
}

.team-cell-strategy {
  width: 180px;
  flex: none;
}

.team-cell-scenes {
  flex: 1 1 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.team-cell-note {
  width: 150px;
  flex: none;
  color: rgba(0, 0, 0, 0.65);
}

.team-cell-actions {
  width: 190px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.team-row-hint {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
  white-space: normal;
}

.team-muted {
  color: rgba(0, 0, 0, 0.35);
}

.team-drag-handle {
  cursor: grab;
  color: rgba(0, 0, 0, 0.35);
}

.team-drag-handle.disabled {
  cursor: not-allowed;
}

.team-enable-capsule {
  display: inline-flex;
  align-items: center;
  width: 34px;
  height: 18px;
  padding: 0 2px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.18);
  cursor: pointer;
}

.team-enable-capsule.active {
  background: var(--ant-color-primary, #1677ff);
}

.team-enable-capsule.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.team-enable-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s ease;
}

.team-enable-capsule.active .team-enable-dot {
  transform: translateX(16px);
}

.team-field-tip {
  margin: 4px 0 0;
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.scene-cond {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
