<template>
  <div class="cultivate-editor">
    <!-- 接管提示：后端注入时写入，非空表示养成接管中、库存保持暂停 -->
    <a-alert
      v-if="formData.Data?.CultivateNotice"
      :message="formData.Data.CultivateNotice"
      type="warning"
      show-icon
      class="cultivate-alert"
    />
    <a-alert
      :message="t('edit.maaCultivateRecognitionHint')"
      type="info"
      show-icon
      class="cultivate-alert"
    />
    <a-alert
      v-if="operatorOptionsError"
      :message="operatorOptionsError"
      type="warning"
      show-icon
      class="cultivate-alert"
    />

    <!-- 跳过开关：作用于整个养成计划，置顶展示（绑定面板上方） -->
    <div class="cultivate-skips">
      <a-checkbox
        :checked="formData.Task?.CultivateSkipDuringActivity"
        :disabled="loading"
        @change="emit('save', 'Task.CultivateSkipDuringActivity', $event.target.checked)"
      >
        {{ t('edit.maaCultivateSkipActivity') }}
      </a-checkbox>
      <a-checkbox
        :checked="formData.Task?.CultivateSkipDuringResourceCollection"
        :disabled="loading"
        @change="emit('save', 'Task.CultivateSkipDuringResourceCollection', $event.target.checked)"
      >
        {{ t('edit.maaCultivateSkipResource') }}
      </a-checkbox>
    </div>

    <!-- 绑定面板与干员选择器并排一行：专精/模组目标的练度与达成检测来自
         森空岛（决策 37/38） -->
    <div class="cultivate-top">
      <div class="cultivate-skland">
        <a-form-item class="cultivate-skland-item">
          <template #label>
            <LabelWithHint
              :text="t('edit.maaCultivateSklandTitle')"
              :hint="t('edit.maaCultivateSklandHint')"
            />
          </template>
          <a-select
            :value="sklandBoundComposite"
            :options="sklandRoleOptionsWithBound"
            :loading="sklandRoleLoading"
            :placeholder="t('edit.maaCultivateSklandRole')"
            :disabled="loading"
            allow-clear
            :get-popup-container="getPopupContainer"
            @dropdown-visible-change="onRoleDropdownVisible"
            @change="handleSklandRoleChange"
          />
          <div v-if="sklandRoleError" class="skland-feedback skland-error">
            {{ sklandRoleError }}
          </div>
          <div v-if="!sklandBound" class="skland-feedback skland-hint">
            {{ t('edit.maaCultivateSklandUnboundHint') }}
          </div>
        </a-form-item>
      </div>

      <a-form-item class="cultivate-picker">
        <template #label>
          <LabelWithHint
            :text="t('edit.maaCultivatePickOperators')"
            :hint="t('edit.maaCultivatePickOperatorsHint')"
          />
        </template>
        <a-select
          :value="null"
          :options="pickerOptions"
          :loading="operatorOptionsLoading"
          :disabled="loading || operatorOptionsLoading || availableOperatorOptions.length === 0"
          :placeholder="operatorPlaceholder"
          show-search
          :filter-option="false"
          :virtual="false"
          :get-popup-container="getPopupContainer"
          @search="handleOperatorSearch"
          @change="handleAddOperator"
        />
      </a-form-item>
    </div>

    <div class="cultivate-body">
      <div class="cultivate-main">
        <div v-if="rows.length" class="cultivate-rows">
          <div v-for="row in rows" :key="row.operatorId" class="cultivate-group">
            <div class="group-head">
              <a-button
                class="group-toggle"
                type="text"
                size="small"
                :aria-label="t('edit.maaCultivateToggleGoals')"
                :aria-expanded="!isGroupCollapsed(row)"
                @click="toggleGroup(row.operatorId)"
              >
                {{ isGroupCollapsed(row) ? '▸' : '▾' }}
              </a-button>
              <span
                class="cultivate-name"
                :title="operatorName(row.operatorId)"
                @click="toggleGroup(row.operatorId)"
                >{{ operatorName(row.operatorId) }}</span
              >
              <a-select
                v-if="!eliteLineOf(row).achieved"
                :value="eliteLineOf(row).savedLevel || undefined"
                :options="eliteLineOf(row).options"
                :placeholder="t('edit.maaCultivateGoalNone')"
                allow-clear
                :disabled="eliteLineOf(row).disabled"
                class="goal-level"
                :aria-label="t('edit.maaCultivateGoalElite')"
                @change="(v: unknown) => handleGoalChange(row, 'elite', '', v)"
              />
              <span v-else class="goal-level goal-achieved-level">
                {{ eliteLineOf(row).levelLabel }}
              </span>
              <a-tag v-if="eliteLineOf(row).overLimit" color="warning">
                {{ t('edit.maaCultivateOverLimit') }}
              </a-tag>
              <a-button
                size="small"
                danger
                :disabled="loading"
                @click="handleRemoveOperator(row.operatorId)"
              >
                {{ t('edit.maaCultivateRemove') }}
              </a-button>
            </div>
            <div class="group-elite-current">
              <span
                class="goal-current"
                :title="
                  eliteLineOf(row).currentUnknown
                    ? t('edit.maaCultivateCurrentUnknownHint')
                    : undefined
                "
                >{{ eliteLineOf(row).current }}</span
              >
            </div>
            <!-- 目标列表：选中干员即列出全部专精+全部模组（精英化在标题行），
                 每个目标一行：选择器 → 超限 → 名称 → 当前 → 状态；未设目标=
                 空选项（清空即移除），没有添加/删除流程。未绑定时只读：配置
                 里的目标不因绑定失效而在界面上消失，仍可见可清，避免留下
                 看不见又清不掉的条目 -->
            <div v-show="!isGroupCollapsed(row)">
              <div v-for="group in goalGridsOf(row)" :key="group.kind" class="goal-list">
                <div v-for="line in group.lines" :key="line.key" class="goal-row">
                  <span class="goal-kind" :title="line.label">{{ line.label }}</span>
                  <span
                    class="goal-current"
                    :title="
                      line.currentUnknown ? t('edit.maaCultivateCurrentUnknownHint') : undefined
                    "
                    >{{ line.current }}</span
                  >
                  <a-tag v-if="line.overLimit" color="warning">
                    {{ t('edit.maaCultivateOverLimitShort') }}
                  </a-tag>
                  <a-tag v-if="line.state" :color="line.state.color">
                    {{ t(line.state.i18n) }}
                  </a-tag>
                  <a-select
                    :value="line.savedLevel || undefined"
                    :options="line.options"
                    :placeholder="t('edit.maaCultivateGoalNone')"
                    allow-clear
                    :disabled="line.disabled"
                    class="goal-level"
                    @change="(v: unknown) => handleGoalChange(row, group.kind, line.targetId, v)"
                  />
                </div>
              </div>
            </div>
          </div>
          <div v-if="!sklandBound" class="skland-feedback skland-hint">
            {{ t('edit.maaCultivateSklandLockedHint') }}
          </div>
        </div>
        <a-empty
          v-else
          :description="t('edit.maaCultivateEmpty')"
          :image-style="{ height: '48px' }"
        />
      </div>
      <div class="cultivate-side">
        <div v-if="rows.length" class="cultivate-preview">
          <div class="preview-header">
            <span class="preview-title">{{ t('edit.maaCultivatePreviewTitle') }}</span>
            <a-tag v-if="cultivatePreviewLoading" color="processing">
              {{ t('edit.maaCultivatePreviewComputing') }}
            </a-tag>
          </div>
          <a-alert
            v-if="cultivatePreviewError"
            :message="cultivatePreviewError"
            type="error"
            show-icon
            class="cultivate-alert"
          />
          <a-alert
            v-if="
              cultivatePreview &&
              (!cultivatePreview.hasProgression || !cultivatePreview.hasInventory)
            "
            :message="availabilityNotice"
            type="info"
            show-icon
            class="cultivate-alert"
          />
          <template v-if="cultivatePreview">
            <div v-if="unobtainableText" class="preview-unobtainable">
              {{ t('edit.maaCultivatePreviewUnobtainable') }}：{{ unobtainableText }}
            </div>
            <div class="preview-heading">{{ t('edit.maaCultivatePreviewStageHeading') }}</div>
            <!-- 刷取计划四列：材料名称 → 关卡 → 数量 → 理智（固定列宽对齐） -->
            <div
              v-for="entry in cultivatePreview.stages"
              :key="`s-${entry.itemId}-${entry.stage}`"
              class="preview-line"
            >
              <span class="preview-stage">{{ entry.stage }}</span>
              <span class="preview-item" :title="entry.name || itemName(entry.itemId)">
                {{ entry.name || itemName(entry.itemId) }}
              </span>
              <span class="preview-count">× {{ entry.count }}</span>
              <template v-if="entry.expectedSanity != null">
                <span class="preview-sanity-sym">≈</span>
                <span class="preview-sanity">
                  {{ entry.expectedSanity }} {{ t('edit.maaCultivateSanityUnit') }}
                </span>
              </template>
              <template v-else>
                <span class="preview-sanity-sym" />
                <span class="preview-sanity" />
              </template>
            </div>
            <div v-if="!cultivatePreview.stages.length" class="preview-empty">
              {{ t('edit.maaCultivatePreviewNone') }}
            </div>
            <div
              v-if="cultivatePreview.totalExpectedSanity != null"
              class="preview-line preview-total"
            >
              <span class="preview-item">
                {{ t('edit.maaCultivatePreviewSanityTotal') }}
              </span>
              <span class="preview-sanity">
                ≈ {{ cultivatePreview.totalExpectedSanity }}
                {{ t('edit.maaCultivateSanityUnit') }}
              </span>
            </div>
            <div class="preview-heading">{{ t('edit.maaCultivatePreviewDemandHeading') }}</div>
            <div
              v-for="item in cultivatePreview.demands"
              :key="`d-${item.itemId}`"
              class="preview-line"
            >
              <span class="preview-item" :title="item.name || itemName(item.itemId)">
                {{ item.name || itemName(item.itemId) }}
              </span>
              <span class="preview-count">× {{ item.count }}</span>
            </div>
          </template>
        </div>
      </div>
    </div>
    <a-typography-link
      class="data-source-note"
      href="https://ark.yituliu.cn"
      target="_blank"
      rel="noreferrer"
      @click="handleExternalLink"
    >
      {{ t('edit.maaDataSourceYituliu') }}
    </a-typography-link>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { CultivatePreviewOut } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'
import { computed, onMounted, ref, watch } from 'vue'
import LabelWithHint from './LabelWithHint.vue'
import {
  appendOperator,
  levelOptionsWithSaved,
  listGoals,
  parseCultivateTargets,
  removeGoal,
  removeOperator,
  serializeCultivateTargets,
  setEliteLevel,
  upsertGoal,
  type CultivateGoalKind,
  type CultivateGoalOption as GoalOption,
  type CultivateOperatorCatalogEntry as OperatorCatalogEntry,
  type CultivateTargetRow,
} from './cultivateTargets'

const { t } = useI18n()

type SelectOption = { label: string; value: string }

const props = defineProps<{
  formData: any
  loading: boolean
  /** 干员目录（一图流全量表，含技能/模组名称目录；[] 表示已加载但为空） */
  operatorCatalog: OperatorCatalogEntry[]
  operatorOptionsLoading: boolean
  operatorOptionsError: string
  /** 森空岛绑定下拉：合并所有已配置凭据账号组的角色（决策 37/38） */
  sklandRoleOptions: SelectOption[]
  sklandRoleLoading: boolean
  sklandRoleError: string
  /** 按需加载角色列表（下拉首次展开时触发） */
  loadSklandRoleOptions: () => Promise<void>
  /** 物品目录（MAA item_index，供预览材料名显示） */
  itemOptions: SelectOption[]
  /** 养成需求预览（后端纯计算结果） */
  cultivatePreview: CultivatePreviewOut | null
  cultivatePreviewLoading: boolean
  cultivatePreviewError: string
  /** 目标行变化时触发（父级负责请求与竞态守卫） */
  loadCultivatePreview: (targetsJson: string) => Promise<void>
}>()

const emit = defineEmits<{ save: [key: string, value: any] }>()

const rows = ref<CultivateTargetRow[]>([])
// 本组件刚序列化写回的 JSON：watch 回声时跳过重建，避免下拉与行列表闪变
let lastEmitted: string | null = null

watch(
  () => props.formData?.Task?.CultivateTargets,
  json => {
    if (json === lastEmitted) return
    rows.value = parseCultivateTargets(json)
    lastEmitted = null
  },
  { immediate: true }
)

const persist = (next: CultivateTargetRow[]) => {
  rows.value = next
  lastEmitted = serializeCultivateTargets(next)
  emit('save', 'Task.CultivateTargets', lastEmitted)
}

const handleAddOperator = (operatorId: string) => {
  if (!operatorId) return
  operatorSearch.value = ''
  persist(
    appendOperator(
      rows.value,
      operatorId,
      [],
      catalogEntryById.value.get(operatorId)?.maxElite ?? 2
    )
  )
}

// 搜索驱动 + 截断：427 条全量目录参与搜索，列表只显示前 10 条（对齐关卡候选的
// top-10 口径）；内置过滤关闭（filter-option false），过滤由 pickerOptions 完成
const operatorSearch = ref('')
const handleOperatorSearch = (value: string) => {
  operatorSearch.value = value
}
const pickerOptions = computed(() => {
  const text = operatorSearch.value.trim().toLowerCase()
  const matched = text
    ? availableOperatorOptions.value.filter(
        option =>
          option.label.toLowerCase().includes(text) || option.value.toLowerCase().includes(text)
      )
    : availableOperatorOptions.value
  return matched.slice(0, 10)
})

const handleRemoveOperator = (operatorId: string) => {
  persist(removeOperator(rows.value, operatorId))
}

// ── 森空岛绑定 ──
const sklandBound = computed(
  () => !!props.formData?.Task?.CultivateSklandAccount && !!props.formData?.Task?.CultivateSklandUid
)
// 选项 value 为 "账号组UUID|游戏uid" 复合值：选中即拆回两个字段保存
const sklandBoundComposite = computed(() => {
  const account = String(props.formData?.Task?.CultivateSklandAccount ?? '')
  const uid = String(props.formData?.Task?.CultivateSklandUid ?? '')
  return account && uid ? `${account}|${uid}` : undefined
})
const sklandRoleOptionsWithBound = computed(() => {
  const bound = sklandBoundComposite.value
  if (!bound || props.sklandRoleOptions.some(option => option.value === bound)) {
    return props.sklandRoleOptions
  }
  // 选项未加载时的兜底项：只标「已绑定角色」，不暴露 uid
  return [
    { label: t('edit.maaCultivateSklandBoundRole'), value: bound },
    ...props.sklandRoleOptions,
  ]
})
const handleSklandRoleChange = (value: unknown) => {
  const composite = String(value ?? '')
  if (!composite) {
    // 清空 = 解除绑定（后端按两个字段均为空视为未绑定）
    emit('save', 'Task.CultivateSklandAccount', '')
    emit('save', 'Task.CultivateSklandUid', '')
    return
  }
  const separator = composite.indexOf('|')
  if (separator <= 0) return
  emit('save', 'Task.CultivateSklandAccount', composite.slice(0, separator))
  emit('save', 'Task.CultivateSklandUid', composite.slice(separator + 1))
}
const onRoleDropdownVisible = (visible: boolean) => {
  if (visible && !props.sklandRoleLoading && !props.sklandRoleOptions.length) {
    props.loadSklandRoleOptions()
  }
}

// ── 目标组：精英化 + 专精/模组 goal 行 ──
const GOAL_STATE_BADGE: Record<string, { i18n: string; color: string }> = {
  in_progress: { i18n: 'edit.maaCultivateStateInProgress', color: 'processing' },
  achieved: { i18n: 'edit.maaCultivateStateAchieved', color: 'success' },
  pending_confirm: { i18n: 'edit.maaCultivateStatePending', color: 'warning' },
}
const goalStateBadge = (state: string) => GOAL_STATE_BADGE[state] ?? null

const goalsOf = (row: CultivateTargetRow, kind: CultivateGoalKind) => listGoals(row.rawGoals, kind)

const eliteLevelOf = (row: CultivateTargetRow) => goalsOf(row, 'elite')[0]?.toLevel ?? null

const catalogEntryById = computed(
  () => new Map(props.operatorCatalog.map(entry => [entry.value, entry]))
)

const savedGoalOf = (row: CultivateTargetRow, kind: CultivateGoalKind, targetId: string) =>
  goalsOf(row, kind).find(goal => goal.targetId === targetId)

const mutateRow = (operatorId: string, mutate: (rawGoals: unknown[]) => unknown[]) => {
  persist(
    rows.value.map(row =>
      row.operatorId === operatorId ? { ...row, rawGoals: mutate(row.rawGoals) } : row
    )
  )
}

// 统一目标改写：选档=写入/更新，清空=移除（elite 复用 setEliteLevel 的 0=null 口径）
const handleGoalChange = (
  row: CultivateTargetRow,
  kind: CultivateGoalKind,
  targetId: string,
  event: unknown
) => {
  const level = Number(event)
  mutateRow(row.operatorId, raw =>
    kind === 'elite'
      ? setEliteLevel(raw, level || null)
      : level
        ? upsertGoal(raw, { kind, targetId, toLevel: level })
        : removeGoal(raw, kind, targetId)
  )
}

// 已添加的干员不再出现在选择器里（Set 查找，目录 427 条 × 目标行）；
// 无任何可达目标的干员（1/2/3★ 与上游缺数据者）列出但不可选并说明原因——
// 直接隐藏会让用户以为目录缺人（决策 40）
const selectedOperatorIds = computed(() => new Set(rows.value.map(row => row.operatorId)))
const noGoalReason = (entry: OperatorCatalogEntry): string =>
  t(entry.dataMissing ? 'edit.maaCultivateNoGoalDataMissing' : 'edit.maaCultivateNoGoalTier')
const availableOperatorOptions = computed(() =>
  props.operatorCatalog
    .filter(option => !selectedOperatorIds.value.has(option.value))
    .map(option =>
      option.maxElite > 0 || option.skills.length || option.modules.length
        ? { label: option.label, value: option.value }
        : {
            label: `${option.label}（${noGoalReason(option)}）`,
            value: option.value,
            disabled: true,
          }
    )
)

const operatorPlaceholder = computed(() =>
  availableOperatorOptions.value.length
    ? t('edit.maaCultivatePickOperators')
    : t('edit.maaCultivateNoOperators')
)

const operatorLabelById = computed(
  () => new Map(props.operatorCatalog.map(option => [option.value, option.label]))
)
const operatorName = (operatorId: string) => operatorLabelById.value.get(operatorId) ?? operatorId

// 每个干员组独立折叠（默认展开）：标题行保留精英化信息，专精/模组九宫格可收起
const collapsedGroups = ref<Set<string>>(new Set())
const isGroupCollapsed = (row: CultivateTargetRow) => collapsedGroups.value.has(row.operatorId)
const toggleGroup = (operatorId: string) => {
  const next = new Set(collapsedGroups.value)
  if (next.has(operatorId)) {
    next.delete(operatorId)
  } else {
    next.add(operatorId)
  }
  collapsedGroups.value = next
}

// 精英化只有精 1/精 2 两档；可达上限来自目录（决策 40），0 = 不设可选档位
const ELITE_LABEL_KEYS: Record<number, string> = {
  1: 'edit.maaCultivateElite1',
  2: 'edit.maaCultivateElite2',
}
const maxEliteOf = (row: CultivateTargetRow) =>
  catalogEntryById.value.get(row.operatorId)?.maxElite ?? 2

// 已存超限档位（数据波动导致）保留在选项里回显，标记"不会被自动刷取"，
// 不因数据变化删用户配置；未设目标走下拉 placeholder+clear（0 档不再是选项）
const eliteLevelOptionsFor = (row: CultivateTargetRow) => {
  const max = maxEliteOf(row)
  return levelOptionsWithSaved(max, eliteLevelOf(row) ?? 0).map(level => {
    const key = ELITE_LABEL_KEYS[level]
    return { label: key ? t(key) : String(level), value: level }
  })
}
const eliteOverLimit = (row: CultivateTargetRow) => (eliteLevelOf(row) ?? 0) > maxEliteOf(row)

const goalOptionOf = (row: CultivateTargetRow, kind: CultivateGoalKind, targetId: string) => {
  const entry = catalogEntryById.value.get(row.operatorId)
  const options = kind === 'mastery' ? (entry?.skills ?? []) : (entry?.modules ?? [])
  return options.find(option => option.value === targetId)
}
const savedGoalLevel = (row: CultivateTargetRow, kind: CultivateGoalKind, targetId: string) =>
  goalsOf(row, kind).find(goal => goal.targetId === targetId)?.toLevel ?? 0

const goalLevelOptionsFor = (
  row: CultivateTargetRow,
  kind: CultivateGoalKind,
  targetId: string
) => {
  const max = goalOptionOf(row, kind, targetId)?.maxLevel ?? 3
  return levelOptionsWithSaved(max, savedGoalLevel(row, kind, targetId)).map(level => ({
    value: level,
    label: t(`edit.maaCultivateGoalLevel${level}`),
  }))
}
const goalOverLimit = (row: CultivateTargetRow, kind: CultivateGoalKind, targetId: string) => {
  const max = goalOptionOf(row, kind, targetId)?.maxLevel ?? 3
  return savedGoalLevel(row, kind, targetId) > max
}

// ── 平铺目标行：目录全量（精英化+专精+模组），无需"添加目标" ──
// 已存目标不在目录里（目录缺失/上游未收录）时合成孤儿行兜底，
// 保证不留看不见又清不掉的配置
const itemsOf = (row: CultivateTargetRow, kind: 'mastery' | 'module') => {
  const entry = catalogEntryById.value.get(row.operatorId)
  const options = kind === 'mastery' ? (entry?.skills ?? []) : (entry?.modules ?? [])
  const known = new Set(options.map(option => option.value))
  const orphans = goalsOf(row, kind)
    .filter(goal => !known.has(goal.targetId))
    .map(goal => ({ value: goal.targetId, label: goal.targetId, maxLevel: 3 }))
  return [...options, ...orphans]
}

// 预览带回的目标干员当前练度；source=default 表示无实测数据（按 0 估算）
const progressionOf = (operatorId: string) =>
  props.cultivatePreview?.progressions?.find(item => item.operatorId === operatorId)

interface FlatGoalLine {
  key: string
  kind: CultivateGoalKind
  targetId: string
  options: Array<{ value: number; label: string }>
  savedLevel: number
  /** 达成档位的展示文案（达成行不给下拉，直接显示这个） */
  levelLabel: string
  overLimit: boolean
  label: string
  current: string
  currentUnknown: boolean
  state: { i18n: string; color: string } | null
  disabled: boolean
  achieved: boolean
  /** 当前已达档位上限（设任何目标都会被立即达成，行不需要显示） */
  maxed: boolean
}

type ProgressionInfo = ReturnType<typeof progressionOf>

const currentUnknownOf = (prog: ProgressionInfo) => !prog || prog.source === 'default'

const currentTextOf = (
  prog: ProgressionInfo,
  kind: CultivateGoalKind,
  targetId: string
): string => {
  if (currentUnknownOf(prog)) {
    return t('edit.maaCultivateCurrentUnknown')
  }
  if (kind === 'elite') {
    return `${t('edit.maaCultivateCurrent')} 精 ${prog!.elite}`
  }
  const levels = kind === 'mastery' ? prog!.masteries : prog!.modules
  return `${t('edit.maaCultivateCurrent')} ${levels?.[targetId] ?? 0}`
}

// 当前档位数值；练度未知（source=default）返回 null（无法判定达成）
const currentLevelOf = (
  prog: ProgressionInfo,
  kind: CultivateGoalKind,
  targetId: string
): number | null => {
  if (currentUnknownOf(prog)) return null
  if (kind === 'elite') return prog!.elite
  const levels = kind === 'mastery' ? prog!.masteries : prog!.modules
  return levels?.[targetId] ?? 0
}

// 达成判定：存的目标档位已被当前练度覆盖（编辑器即时判定，不等后端运行标记）；
// 达成行灰掉下拉只展示档位，避免"当前 3 / 目标三级"却仍可改的违和
const achievedOf = (
  prog: ProgressionInfo,
  kind: CultivateGoalKind,
  targetId: string,
  savedLevel: number,
  savedState: string | null
): boolean => {
  if (savedState === 'achieved') return true
  if (!savedLevel) return false
  const current = currentLevelOf(prog, kind, targetId)
  return current !== null && current >= savedLevel
}

const eliteLineOf = (row: CultivateTargetRow): FlatGoalLine => {
  const prog = progressionOf(row.operatorId)
  const saved = savedGoalOf(row, 'elite', '')
  const savedLevel = saved?.toLevel ?? 0
  const achieved = achievedOf(prog, 'elite', '', savedLevel, saved?.state ?? null)
  const eliteKey = ELITE_LABEL_KEYS[savedLevel]
  const currentElite = currentLevelOf(prog, 'elite', '')
  const maxElite = maxEliteOf(row)
  return {
    key: 'elite',
    kind: 'elite',
    targetId: '',
    options: eliteLevelOptionsFor(row),
    savedLevel,
    levelLabel: savedLevel ? (eliteKey ? t(eliteKey) : String(savedLevel)) : '',
    overLimit: eliteOverLimit(row),
    label: t('edit.maaCultivateGoalElite'),
    current: currentTextOf(prog, 'elite', ''),
    currentUnknown: currentUnknownOf(prog),
    state: null,
    disabled: props.loading || achieved,
    achieved,
    maxed: currentElite !== null && maxElite >= 1 && currentElite >= maxElite,
  }
}

const itemLinesOf = (row: CultivateTargetRow, kind: 'mastery' | 'module'): FlatGoalLine[] => {
  const prog = progressionOf(row.operatorId)
  const unknown = currentUnknownOf(prog)
  return itemsOf(row, kind).map(item => {
    const saved = savedGoalOf(row, kind, item.value)
    const savedLevel = saved?.toLevel ?? 0
    const achieved = achievedOf(prog, kind, item.value, savedLevel, saved?.state ?? null)
    // 当前已是满级：任何目标都会被立即判定达成，行本身没有可做的事
    const current = currentLevelOf(prog, kind, item.value)
    const maxLevel = goalOptionOf(row, kind, item.value)?.maxLevel ?? 3
    return {
      key: `${kind === 'mastery' ? 'm' : 'e'}-${item.value}`,
      kind,
      targetId: item.value,
      options: goalLevelOptionsFor(row, kind, item.value),
      savedLevel,
      levelLabel:
        savedLevel >= 1 && savedLevel <= 3
          ? t(`edit.maaCultivateGoalLevel${savedLevel}`)
          : String(savedLevel),
      overLimit: goalOverLimit(row, kind, item.value),
      label: item.label,
      current: currentTextOf(prog, kind, item.value),
      currentUnknown: unknown,
      // 后端未及时打标时按当前练度即时补「已达成」徽标
      state: saved
        ? (goalStateBadge(saved.state) ?? (achieved ? GOAL_STATE_BADGE.achieved : null))
        : null,
      disabled: props.loading || !sklandBound.value || achieved,
      achieved,
      maxed: !unknown && current !== null && maxLevel >= 1 && current >= maxLevel,
    }
  })
}

// 专精/模组各自成列表；空组（该干员无模组等）不渲染。
// 已达成行直接隐藏：后端会在下次注入时自动移除该目标，不必占界面；
// 满级行（当前已达档位上限）同样隐藏——设任何目标都会被立即达成，没有可做的事
const goalGridsOf = (row: CultivateTargetRow) =>
  (['mastery', 'module'] as const)
    .map(kind => ({
      kind,
      lines: itemLinesOf(row, kind).filter(line => !line.achieved && !line.maxed),
    }))
    .filter(grid => grid.lines.length)

// 目标行变化 → 防抖后请求需求预览（竞态守卫在父级加载器里）。
// 组件随 PipelineRow 展开销毁重建：重进页面/重新展开时 rows 不再变化，
// 不会触发 watch，须在挂载时对已保存的目标主动拉一次预览
let previewTimer: number | undefined
watch(rows, nextRows => {
  if (previewTimer) window.clearTimeout(previewTimer)
  previewTimer = window.setTimeout(() => {
    if (!nextRows.length) return
    props.loadCultivatePreview(serializeCultivateTargets(nextRows))
  }, 600)
})

onMounted(() => {
  if (rows.value.length) {
    props.loadCultivatePreview(serializeCultivateTargets(rows.value))
  }
  // 已绑定时拉一次角色列表以回显角色名（未绑定不请求；下拉展开也会刷新）
  if (sklandBound.value) {
    props.loadSklandRoleOptions()
  }
})

const unobtainableText = computed(() =>
  (props.cultivatePreview?.unobtainable ?? [])
    .map((item: { itemId: string; name?: string }) => item.name || itemName(item.itemId))
    .join('、')
)

const itemLabelById = computed(
  () => new Map(props.itemOptions.map(option => [option.value, option.label]))
)
const itemName = (itemId: string) => itemLabelById.value.get(itemId) ?? itemId

// 干员/仓库识别档案缺失时预览按精0+空库存估算：明示估算口径，避免把偏大
// 的需求数字当成精确值（方案 §4.3 预览须注明"以识别后为准"）
const availabilityNotice = computed(() => {
  if (!props.cultivatePreview) return ''
  const missing: string[] = []
  if (!props.cultivatePreview.hasProgression) missing.push(t('edit.maaCultivateMissingProgression'))
  if (!props.cultivatePreview.hasInventory) missing.push(t('edit.maaCultivateMissingInventory'))
  if (!missing.length) return ''
  return `${t('edit.maaCultivateEstimatePrefix')}${missing.join(
    t('edit.maaCultivateEstimateJoin')
  )}${t('edit.maaCultivateEstimateSuffix')}`
})

// 下拉浮层挂编辑器根容器：挂 body 时页面滚动浮层驻留原地不跟随（与
// DepotMaintainPlanEditor 同款，PR1 下拉污染三根因的①）
const getPopupContainer = (trigger: HTMLElement): HTMLElement =>
  trigger.closest<HTMLElement>('.cultivate-editor') ?? document.body
</script>

<style scoped>
/* 绑定面板与干员选择器并排一行（窄屏自动换行堆叠）；
   与上方跳过开关之间加分隔线过渡 */
.cultivate-top {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary, #f0f0f0);
  margin-bottom: 12px;
}

/* 表单元素默认带 24px 底边距，会顶出双倍间隙（与跳过计划-分隔线的间距不一致），清零 */
.cultivate-top .cultivate-skland-item {
  margin-bottom: 0;
}

.cultivate-top > .cultivate-skland,
.cultivate-top > .cultivate-picker {
  flex: 1 1 380px;
  min-width: 0;
  margin-bottom: 0;
}

.cultivate-skland {
  margin-bottom: 8px;
}

/* 绑定面板与干员选择器单行化：标签在左，控件在右侧展开（默认是上下两行）。
   antd 竖排表单会用更高优先级把行方向写成 column，这里前缀 + 显式 row 压回 */
.cultivate-skland .cultivate-skland-item :deep(.ant-form-item-row),
.cultivate-editor .cultivate-picker :deep(.ant-form-item-row) {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
}

.cultivate-skland .cultivate-skland-item :deep(.ant-form-item-label),
.cultivate-editor .cultivate-picker :deep(.ant-form-item-label) {
  flex-shrink: 0;
  padding: 0;
  /* 统一标签宽度：两行控件左边缘对齐（取「绑定森空岛」+问号图标的最长宽度） */
  width: 96px;
}

.cultivate-skland .cultivate-skland-item :deep(.ant-form-item-control),
.cultivate-editor .cultivate-picker :deep(.ant-form-item-control) {
  flex: 1;
  min-width: 0;
}

.skland-feedback {
  margin-top: 4px;
  font-size: 12px;
}

.skland-error {
  color: var(--ant-error-color, #cf1322);
}

.skland-hint {
  opacity: 0.65;
}

.cultivate-group {
  border: 1px solid var(--ant-border-color-split, #f0f0f0);
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 8px;
}

.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

/* 名称占最左并吸收余量（精英化控件被推到右侧），点名称或箭头收起/展开目标 */
.group-head .cultivate-name {
  flex: 1;
  cursor: pointer;
}

/* 折叠箭头：最左、紧凑；移除按钮独占最右 */
.group-head .group-toggle {
  flex-shrink: 0;
  width: 22px;
  min-width: 22px;
  margin: 0;
  padding: 0;
  color: var(--ant-color-text-secondary);
}

.group-head > .ant-btn:last-child {
  margin-left: auto;
}

/* 标题行：干员名在左，目标下拉与移除在右（干员名可点收起/展开） */
.group-head .goal-level {
  width: 96px;
  flex-shrink: 0;
}

/* 当前精英等级：独立一行，与「精英化」标签左对齐（箭头 22px + 间距 8px） */
.group-elite-current {
  /* 紧跟标题行（当前精英等级），下方留白交给分组内边距 */
  margin: 0 0 0 30px;
}

.goal-kind {
  /* 名称列在档位选择器右侧，自然宽度；超长省略号截断，完整名走 title 悬停 */
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.85;
}

.goal-current {
  flex-shrink: 0;
  font-size: 12px;
  opacity: 0.55;
}

/* 目标列表：每个目标一行 选择器 → 超限 → 名称 → 当前 → 状态；
   左缩进与标题行的「精英化」标签对齐（箭头 22 + 间距 8） */
.goal-list {
  display: flex;
  flex-direction: column;
  margin: 2px 0 0;
  padding-left: 30px;
}

.goal-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  min-width: 0;
}

/* 宽度压住父级 :deep(.ant-select){width:100%}，档位下拉固定 96px */
.goal-row .goal-level {
  width: 96px;
  flex-shrink: 0;
}

/* 达成行不给下拉：静态显示达成档位（占位宽度与下拉一致，保持列对齐） */
.goal-achieved-level {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  color: var(--ant-color-text-secondary);
}

/* 名称占满余量（超长省略号），状态标签钉在行尾成列 */
.goal-row .goal-kind {
  flex: 1;
}

.cultivate-alert {
  margin-bottom: 12px;
}

.cultivate-picker {
  margin-bottom: 12px;
}

.cultivate-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cultivate-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ant-color-text);
}

/* 一图流数据署名（CC BY-NC 4.0 授权条件，方案 §5.4/决策 3）；链接走系统浏览器 */
.data-source-note {
  margin-top: 8px;
  font-size: 12px;
}

/* 427 条长列表：全量渲染防 rc-virtual-list 混渲染，contain 防滚动链式带动整页
   （与 DepotMaintainPlanEditor 同款，PR1 下拉污染三根因的②③） */
.cultivate-editor :deep(.rc-virtual-list-holder) {
  overscroll-behavior: contain;
}

.cultivate-skips {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}

/* 左：干员与目标列表；右：预计需要材料预览（窄屏自动换行堆叠）。
   顶部控件区与双栏之间加分隔线过渡 */
.cultivate-body {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
  margin-top: 0;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}

.cultivate-main {
  flex: 1 1 420px;
  min-width: 0;
}

.cultivate-side {
  flex: 1 1 420px;
  min-width: 0;
}

.cultivate-preview {
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.preview-title {
  font-weight: 600;
  color: var(--ant-color-text);
}

.preview-heading {
  margin: 8px 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.preview-line {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 0;
  font-size: 13px;
  color: var(--ant-color-text);
}

/* 刷取计划四列固定宽：名称占余量，关卡/数量/理智成列（含空理智占位保持对齐） */
.preview-stage {
  width: 64px;
  flex-shrink: 0;
  color: var(--ant-color-text-secondary);
}

.preview-line .preview-count {
  width: 64px;
  flex-shrink: 0;
  text-align: left;
}

/* ≈ 符号与理智值各自成列（空值行留空占位保持对齐） */
.preview-sanity-sym {
  width: 20px;
  flex-shrink: 0;
  text-align: left;
  color: var(--ant-color-text-secondary);
}

.preview-line .preview-sanity {
  width: 96px;
  flex-shrink: 0;
  text-align: right;
}

.preview-item {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-count {
  color: var(--ant-color-text-secondary);
}

.preview-sanity {
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.preview-total {
  margin-top: 4px;
  font-weight: 600;
}

.preview-unobtainable {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--ant-color-warning);
}

.preview-empty {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
