<template>
  <div class="cultivate-page-editor">
    <div class="cultivate-toolbar">
      <div class="cultivate-toggle">
        <a-switch
          :aria-label="t('edit.maaCultivate')"
          :checked="formData.Task?.IfCultivate ?? false"
          :disabled="editorLoading"
          @change="emit('save', 'Task.IfCultivate', $event)"
        />
        <span>{{ t('edit.maaCultivate') }}</span>
      </div>
      <div class="cultivate-account cultivate-skland">
        <span class="cultivate-account-label">{{ t('edit.maaCultivateSklandTitle') }}</span>
        <a-select
          :aria-label="t('edit.maaCultivateSklandTitle')"
          :value="sklandBoundComposite"
          :options="sklandRoleOptionsWithBound"
          :loading="sklandRoleLoading"
          :placeholder="t('edit.maaCultivateSklandRole')"
          :disabled="editorLoading"
          allow-clear
          :get-popup-container="getPopupContainer"
          :list-height="popupListHeight"
          @dropdown-visible-change="onRoleDropdownVisible"
          @change="handleSklandRoleChange"
        />
      </div>
      <a-popover :title="t('maaCopilot.executionSettings')" trigger="click" placement="bottomRight">
        <template #content>
          <div class="cultivate-execution-settings">
            <a-checkbox
              :checked="formData.Task?.CultivateAutoRaise ?? false"
              :disabled="editorLoading"
              @change="emit('save', 'Task.CultivateAutoRaise', $event.target.checked)"
              >{{ t('edit.maaCultivateAutoRaise') }}</a-checkbox
            >
            <a-checkbox
              :checked="formData.Task?.CultivateSkipDuringActivity"
              :disabled="editorLoading"
              @change="emit('save', 'Task.CultivateSkipDuringActivity', $event.target.checked)"
              >{{ t('edit.maaCultivateSkipActivity') }}</a-checkbox
            >
            <a-checkbox
              :checked="formData.Task?.CultivateSkipDuringResourceCollection"
              :disabled="editorLoading"
              @change="
                emit('save', 'Task.CultivateSkipDuringResourceCollection', $event.target.checked)
              "
              >{{ t('edit.maaCultivateSkipResource') }}</a-checkbox
            >
            <p class="skland-hint">{{ t('edit.maaCultivateAutoRaiseVersionHint') }}</p>
          </div>
        </template>
        <a-button class="cultivate-settings-button">
          <template #icon><SettingOutlined aria-hidden="true" /></template>
          {{ t('maaCopilot.executionSettings') }}
        </a-button>
      </a-popover>
    </div>
    <div v-if="sklandRoleError" class="skland-feedback skland-error">{{ sklandRoleError }}</div>
    <a-alert
      v-if="formData.Data?.CultivateNotice"
      :message="formData.Data.CultivateNotice"
      type="warning"
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
    <a-tabs v-model:active-key="activeTab">
      <a-tab-pane key="targets" :tab="t('maaCopilot.targetsTab')">
        <div class="cultivate-editor">
          <a-alert
            :message="t('edit.maaCultivateRecognitionHint')"
            type="info"
            show-icon
            class="cultivate-alert"
          />
          <div class="skland-feedback skland-hint cultivate-mastery-hint">
            <div>{{ t('edit.maaCultivateAutoRaiseHint') }}</div>
            <div>{{ t('edit.maaCultivateMasterySkillHint') }}</div>
          </div>
          <div class="cultivate-top">
            <div v-if="!sklandBound" class="skland-feedback skland-hint">
              {{ t('edit.maaCultivateSklandUnboundHint') }}
            </div>
            <a-form-item class="cultivate-picker">
              <template #label>
                <LabelWithHint
                  :text="t('edit.maaCultivatePickOperators')"
                  :hint="t('edit.maaCultivatePickOperatorsHint')"
                />
              </template>
              <div class="cultivate-picker-actions">
                <a-select
                  :value="null"
                  :options="pickerOptions"
                  :loading="operatorOptionsLoading"
                  :disabled="
                    editorLoading || operatorOptionsLoading || availableOperatorOptions.length === 0
                  "
                  :placeholder="operatorPlaceholder"
                  show-search
                  :filter-option="false"
                  :virtual="false"
                  :get-popup-container="getPopupContainer"
                  :list-height="popupListHeight"
                  @search="handleOperatorSearch"
                  @change="handleAddOperator"
                />
                <CultivateClipboardImport
                  :disabled="loading"
                  :import-targets="importCultivateTargets"
                  @busy="importing = $event"
                  @imported="expandImportedOperators"
                />
              </div>
            </a-form-item>
          </div>

          <div class="cultivate-target-actions">
            <a-input
              v-model:value="operatorFilter"
              class="cultivate-target-search"
              :placeholder="t('edit.maaCultivateSearchOperators')"
              :aria-label="t('edit.maaCultivateSearchOperators')"
              allow-clear
            >
              <template #prefix><SearchOutlined aria-hidden="true" /></template>
            </a-input>
            <a-space wrap>
              <a-checkbox
                :checked="allOperatorsSelected"
                :indeterminate="selectedVisibleCount > 0 && !allOperatorsSelected"
                :disabled="editorLoading || !filteredRows.length"
                @change="selectAllOperators($event.target.checked)"
              >
                {{
                  t(
                    operatorFilter.trim()
                      ? 'edit.maaCultivateSelectMatches'
                      : 'edit.maaCultivateSelectAll'
                  )
                }}
              </a-checkbox>
              <a-button
                danger
                :disabled="editorLoading || !operatorSelection.size"
                @click="removeSelectedOperators"
              >
                {{ t('edit.maaCultivateDeleteSelected', { count: operatorSelection.size }) }}
              </a-button>
            </a-space>
            <a-space class="cultivate-module-toggle">
              <a-switch
                v-model:checked="showModules"
                :disabled="editorLoading"
                :aria-label="t('edit.maaCultivateShowModules')"
              />
              <span>{{ t('edit.maaCultivateShowModules') }}</span>
            </a-space>
          </div>

          <div class="cultivate-body">
            <div class="cultivate-main">
              <a-pagination
                v-if="filteredRows.length > OPERATOR_PAGE_SIZE"
                v-model:current="operatorPage"
                class="cultivate-pagination"
                size="small"
                :page-size="OPERATOR_PAGE_SIZE"
                :total="filteredRows.length"
                :show-size-changer="false"
                :disabled="editorLoading"
              />
              <div v-if="filteredRows.length" class="cultivate-rows">
                <div v-for="row in visibleRows" :key="row.operatorId" class="cultivate-group">
                  <div class="group-head">
                    <a-checkbox
                      :checked="operatorSelection.has(row.operatorId)"
                      :disabled="editorLoading"
                      :aria-label="
                        t('edit.maaCultivateSelectOperator', { name: operatorName(row.operatorId) })
                      "
                      @change="toggleOperatorSelection(row.operatorId, $event.target.checked)"
                    />
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
                      v-if="!row.elite.achieved"
                      :value="row.elite.savedLevel || undefined"
                      :options="row.elite.options"
                      :placeholder="t('edit.maaCultivateGoalNone')"
                      allow-clear
                      :disabled="row.elite.disabled"
                      :get-popup-container="getPopupContainer"
                      :list-height="popupListHeight"
                      class="goal-level"
                      :aria-label="t('edit.maaCultivateGoalElite')"
                      @change="(v: unknown) => handleGoalChange(row, 'elite', '', v)"
                    />
                    <span v-else class="goal-level goal-achieved-level">
                      {{ row.elite.levelLabel }}
                    </span>
                    <a-tag v-if="row.elite.overLimit" color="warning">
                      {{ t('edit.maaCultivateOverLimit') }}
                    </a-tag>
                    <a-button
                      size="small"
                      danger
                      :disabled="editorLoading"
                      @click="handleRemoveOperator(row.operatorId)"
                    >
                      {{ t('edit.maaCultivateRemove') }}
                    </a-button>
                  </div>
                  <div class="group-elite-current">
                    <span
                      class="goal-current"
                      :title="
                        row.elite.currentUnknown
                          ? t('edit.maaCultivateCurrentUnknownHint')
                          : undefined
                      "
                      >{{ row.elite.current }}</span
                    >
                  </div>
                  <!-- 目标列表：技能等级、全部专精和全部模组（精英化在标题行），
                 每个目标一行：名称 → 当前 → 超限/状态标签 → 档位选择器（最右成列）；
                 未设目标=空选项（清空即移除），没有添加/删除流程。未绑定时只读：配置
                 里的目标不因绑定失效而在界面上消失，仍可见可清，避免留下
                 看不见又清不掉的条目 -->
                  <div v-if="!isGroupCollapsed(row)">
                    <div v-for="group in goalGridsOf(row)" :key="group.kind" class="goal-list">
                      <div v-for="line in group.lines" :key="line.key" class="goal-row">
                        <span class="goal-kind" :title="line.label">{{ line.label }}</span>
                        <span
                          class="goal-current"
                          :title="
                            line.currentUnknown
                              ? t('edit.maaCultivateCurrentUnknownHint')
                              : undefined
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
                          :get-popup-container="getPopupContainer"
                          :list-height="popupListHeight"
                          class="goal-level"
                          @change="
                            (v: unknown) => handleGoalChange(row, group.kind, line.targetId, v)
                          "
                        />
                      </div>
                    </div>
                  </div>
                </div>
                <div v-if="!sklandBound" class="skland-feedback skland-hint">
                  {{ t('edit.maaCultivateSklandLockedHint') }}
                </div>
                <div v-else-if="sklandDegraded" class="skland-feedback skland-hint">
                  {{ t('edit.maaCultivateSklandDegradedHint') }}
                </div>
              </div>
              <a-empty
                v-else
                :description="
                  t(
                    operatorFilter.trim()
                      ? 'edit.maaCultivateSearchEmpty'
                      : 'edit.maaCultivateEmpty'
                  )
                "
                :image-style="{ height: '48px' }"
              />
            </div>
            <div class="cultivate-side">
              <CultivatePreviewPanel
                v-if="rows.length"
                :preview="cultivatePreview"
                :loading="cultivatePreviewLoading"
                :error="cultivatePreviewError"
                :item-options="itemOptions"
              />
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
      </a-tab-pane>
      <a-tab-pane key="copilot" :tab="t('maaCopilot.analysisTab')">
        <CopilotCultivatePlanner
          :disabled="editorLoading"
          :bound="sklandBound"
          :binding-key="sklandBoundComposite ?? ''"
          :catalog="operatorCatalog"
          :import-targets="importCultivateTargets"
          :prepare-analysis="prepareCopilotAnalysis"
          @imported="handleCopilotImported"
          @busy="importing = $event"
        />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { SearchOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import type { CultivatePreviewOut } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import LabelWithHint from './LabelWithHint.vue'
import CopilotCultivatePlanner from './CopilotCultivatePlanner.vue'
import CultivatePreviewPanel from './CultivatePreviewPanel.vue'
import CultivateClipboardImport from './CultivateClipboardImport.vue'
import { usePlanSelectPopup } from './usePlanSelectPopup'
import {
  appendOperator,
  levelOptionsWithSaved,
  listGoals,
  parseCultivateTargets,
  removeGoal,
  removeOperator,
  serializeCultivateTargets,
  setEliteLevel,
  setMasteryLevel,
  upsertGoal,
  type CultivateGoalKind,
  type CultivateGoalOption as GoalOption,
  type CultivateOperatorCatalogEntry as OperatorCatalogEntry,
  type CultivateTargetRow,
  type CultivateImportResult,
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
  importCultivateTargets: (
    content: string,
    format?: 'clipboard' | 'targets'
  ) => Promise<CultivateImportResult>
  prepareCopilotAnalysis: () => Promise<void>
}>()

const emit = defineEmits<{ save: [key: string, value: any] }>()

const activeTab = ref('targets')
const handleCopilotImported = (operatorIds: string[]) => {
  expandImportedOperators(operatorIds)
  activeTab.value = 'targets'
}
const showModules = ref(false)
const operatorFilter = ref('')
// 目标编辑统一替换数组；不为全量目标创建深层代理，避免保存/预览序列化遍历代理。
const rows = shallowRef<CultivateTargetRow[]>([])
const operatorSelection = ref(new Set<string>())
const allOperatorsSelected = computed(
  () => filteredRows.value.length > 0 && selectedVisibleCount.value === filteredRows.value.length
)
const selectedVisibleCount = computed(
  () => filteredRows.value.filter(row => operatorSelection.value.has(row.operatorId)).length
)
// 分页只限制渲染，保存与需求预览始终使用全量目标。
const OPERATOR_PAGE_SIZE = 4
const operatorPage = ref(1)
const importing = ref(false)
const editorLoading = computed(() => props.loading || importing.value)
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

watch(rows, nextRows => {
  const remainingIds = new Set(nextRows.map(row => row.operatorId))
  operatorSelection.value = new Set([...operatorSelection.value].filter(id => remainingIds.has(id)))
})

const persist = (next: CultivateTargetRow[]) => {
  rows.value = next
  lastEmitted = serializeCultivateTargets(next)
  emit('save', 'Task.CultivateTargets', lastEmitted)
}

const handleAddOperator = (operatorId: string) => {
  if (!operatorId) return
  operatorSearch.value = ''
  operatorFilter.value = ''
  persist(
    appendOperator(
      rows.value,
      operatorId,
      [],
      catalogEntryById.value.get(operatorId)?.maxElite ?? 2
    )
  )
  operatorPage.value = Math.ceil(rows.value.length / OPERATOR_PAGE_SIZE)
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

const toggleOperatorSelection = (operatorId: string, checked: boolean) => {
  const next = new Set(operatorSelection.value)
  if (checked) next.add(operatorId)
  else next.delete(operatorId)
  operatorSelection.value = next
}

const selectAllOperators = (checked: boolean) => {
  const next = new Set(operatorSelection.value)
  for (const row of filteredRows.value) {
    if (checked) next.add(row.operatorId)
    else next.delete(row.operatorId)
  }
  operatorSelection.value = next
}

const removeSelectedOperators = () => {
  const selected = new Set(operatorSelection.value)
  Modal.confirm({
    title: t('edit.maaCultivateDeleteSelected', { count: selected.size }),
    content: t('edit.maaCultivateDeleteSelectedConfirm', { count: selected.size }),
    okText: t('common.confirm'),
    cancelText: t('common.cancel'),
    okType: 'danger',
    onOk: () => persist(rows.value.filter(row => !selected.has(row.operatorId))),
  })
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
  mutateRow(row.operatorId, raw => {
    if (kind === 'elite') return setEliteLevel(raw, level || null)
    if (kind === 'mastery') return setMasteryLevel(raw, targetId, level || null)
    return level
      ? upsertGoal(raw, { kind, targetId, toLevel: level })
      : removeGoal(raw, kind, targetId)
  })
}

// 已添加的干员不再出现在选择器里（Set 查找，目录 427 条 × 目标行）；
// 无任何可达目标的干员列出但不可选并说明原因——
// 直接隐藏会让用户以为目录缺人（决策 40）
const selectedOperatorIds = computed(() => new Set(rows.value.map(row => row.operatorId)))
const noGoalReason = (entry: OperatorCatalogEntry): string =>
  t(entry.dataMissing ? 'edit.maaCultivateNoGoalDataMissing' : 'edit.maaCultivateNoGoalTier')
const availableOperatorOptions = computed(() =>
  props.operatorCatalog
    .filter(option => !selectedOperatorIds.value.has(option.value))
    .map(option =>
      option.maxElite > 0 ||
      option.maxSkillLevel > 1 ||
      option.skills.length ||
      option.modules.length
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

const filteredRows = computed(() => {
  const query = operatorFilter.value.trim().toLowerCase()
  return query
    ? rows.value.filter(
        row =>
          operatorName(row.operatorId).toLowerCase().includes(query) ||
          row.operatorId.toLowerCase().includes(query)
      )
    : rows.value
})

watch(
  operatorFilter,
  () => {
    operatorPage.value = 1
  },
  { flush: 'sync' }
)
watch(
  () => filteredRows.value.length,
  length => {
    operatorPage.value = Math.min(
      operatorPage.value,
      Math.max(1, Math.ceil(length / OPERATOR_PAGE_SIZE))
    )
  }
)

// 每个干员组独立折叠（默认展开）：标题行保留精英化信息，专精/模组逐行列表可收起
const collapsedGroups = ref<Set<string>>(new Set())
const expandImportedOperators = (operatorIds: string[]) => {
  operatorFilter.value = ''
  const next = new Set(collapsedGroups.value)
  for (const id of operatorIds) next.delete(id)
  collapsedGroups.value = next
  const importedIds = new Set(operatorIds)
  const firstImported = rows.value.findIndex(row => importedIds.has(row.operatorId))
  if (firstImported >= 0) {
    operatorPage.value = Math.floor(firstImported / OPERATOR_PAGE_SIZE) + 1
  }
}
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

// 精英化只有精 0/精 1/精 2 三档；可达上限来自目录（决策 40），0 = 不设可选档位
const ELITE_LABEL_KEYS: Record<number, string> = {
  0: 'edit.maaCultivateElite0',
  1: 'edit.maaCultivateElite1',
  2: 'edit.maaCultivateElite2',
}
const SKILL_LABEL_KEYS: Record<number, string> = {
  1: 'edit.maaCultivateSkill1',
  2: 'edit.maaCultivateSkill2',
  3: 'edit.maaCultivateSkill3',
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

// ── 平铺目标行：目录全量（精英化+技能等级+专精+模组），无需"添加目标" ──
// 已存目标不在目录里（目录缺失/上游未收录）时合成孤儿行兜底，
// 保证不留看不见又清不掉的配置
const itemsOf = (row: CultivateTargetRow, kind: 'mastery' | 'module'): GoalOption[] => {
  const entry = catalogEntryById.value.get(row.operatorId)
  const options = kind === 'mastery' ? (entry?.skills ?? []) : (entry?.modules ?? [])
  const known = new Set(options.map(option => option.value))
  const orphans = goalsOf(row, kind)
    .filter(goal => !known.has(goal.targetId))
    .map(goal => ({ value: goal.targetId, label: goal.targetId, maxLevel: 3 }))
  return [...options, ...orphans]
}

// 预览带回的目标干员当前练度；source=default 表示无实测数据（按 0 估算）
const progressionById = computed(
  () => new Map((props.cultivatePreview?.progressions ?? []).map(item => [item.operatorId, item]))
)
const progressionOf = (operatorId: string) => progressionById.value.get(operatorId)

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

// 精英化只认 local/default 也算未知（无任何档案）；专精/模组只有
// 森空岛/手填源携带观测，local（OperBox 结构性无此字段）与 default
// （兜底）的空表是"未观测"而非"当前 0"，按 0 展示会误导用户重刷已达档位
const MASTERY_MODULE_SOURCES = new Set(['skland', 'manual'])

const currentUnknownOf = (prog: ProgressionInfo) => !prog || prog.source === 'default'

// 专精/模组维度的未知判定：与后端 build_requirements 的暂停口径一致
const dimensionUnknownOf = (prog: ProgressionInfo, kind: CultivateGoalKind) =>
  kind === 'skill'
    ? !MASTERY_MODULE_SOURCES.has(prog?.source ?? 'default') || prog?.skillLevel == null
    : kind !== 'elite' && !MASTERY_MODULE_SOURCES.has(prog?.source ?? 'default')

const currentTextOf = (
  prog: ProgressionInfo,
  kind: CultivateGoalKind,
  targetId: string
): string => {
  const unknown = kind === 'elite' ? currentUnknownOf(prog) : dimensionUnknownOf(prog, kind)
  if (unknown) {
    return t('edit.maaCultivateCurrentUnknown')
  }
  if (kind === 'elite') {
    const eliteLabel = ELITE_LABEL_KEYS[prog!.elite]
    return `${t('edit.maaCultivateCurrent')} ${eliteLabel ? t(eliteLabel) : prog!.elite}`
  }
  if (kind === 'skill') return `${t('edit.maaCultivateCurrent')} ${prog!.skillLevel}`
  const levels = kind === 'mastery' ? prog!.masteries : prog!.modules
  return `${t('edit.maaCultivateCurrent')} ${levels?.[targetId] ?? 0}`
}

// 当前档位数值；维度未知（精英化无档案 / 专精模组非森空岛观测）返回 null
const currentLevelOf = (
  prog: ProgressionInfo,
  kind: CultivateGoalKind,
  targetId: string
): number | null => {
  if (kind === 'elite' ? currentUnknownOf(prog) : dimensionUnknownOf(prog, kind)) return null
  if (kind === 'elite') return prog!.elite
  if (kind === 'skill') return prog!.skillLevel ?? null
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
    disabled: editorLoading.value || achieved,
    achieved,
    maxed: currentElite !== null && maxElite >= 1 && currentElite >= maxElite,
  }
}

// 同一标题多处展示精英化信息，每页只计算一次，避免为每个绑定重复创建选项。
const visibleRows = computed(() =>
  filteredRows.value
    .slice((operatorPage.value - 1) * OPERATOR_PAGE_SIZE, operatorPage.value * OPERATOR_PAGE_SIZE)
    .map(row => ({ ...row, elite: eliteLineOf(row) }))
)

const itemLinesOf = (row: CultivateTargetRow, kind: 'mastery' | 'module'): FlatGoalLine[] => {
  const prog = progressionOf(row.operatorId)
  const unknown = dimensionUnknownOf(prog, kind)
  return itemsOf(row, kind).map(item => {
    const skillLabel = kind === 'mastery' ? SKILL_LABEL_KEYS[item.skillIndex ?? 0] : null
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
      label: skillLabel
        ? t('edit.maaCultivateSkillName', { name: item.label, skill: t(skillLabel) })
        : item.label,
      current: currentTextOf(prog, kind, item.value),
      currentUnknown: unknown,
      // 后端未及时打标时按当前练度即时补「已达成」徽标
      state: saved
        ? (goalStateBadge(saved.state) ?? (achieved ? GOAL_STATE_BADGE.achieved : null))
        : null,
      disabled: editorLoading.value || !sklandBound.value || achieved,
      achieved,
      maxed: !unknown && current !== null && maxLevel >= 1 && current >= maxLevel,
    }
  })
}

// 技能等级、专精与模组各自成列表；空组不渲染。
// 已达成行直接隐藏：后端会在下次注入时自动移除该目标，不必占界面；
// 满级行（当前已达档位上限）同样隐藏——设任何目标都会被立即达成，没有可做的事
const skillLineOf = (row: CultivateTargetRow): FlatGoalLine | null => {
  const maxLevel = catalogEntryById.value.get(row.operatorId)?.maxSkillLevel ?? 0
  const saved = savedGoalOf(row, 'skill', '')
  if (maxLevel <= 1 && !saved) return null
  const savedLevel = saved?.toLevel ?? 0
  const prog = progressionOf(row.operatorId)
  const unknown = dimensionUnknownOf(prog, 'skill')
  const current = currentLevelOf(prog, 'skill', '')
  const achieved = achievedOf(prog, 'skill', '', savedLevel, saved?.state ?? null)
  return {
    key: 'skill',
    kind: 'skill',
    targetId: '',
    options: levelOptionsWithSaved(maxLevel, savedLevel)
      .filter(level => level >= 2)
      .map(level => ({ value: level, label: t('edit.maaCultivateSkillLevel', { level }) })),
    savedLevel,
    levelLabel: savedLevel ? t('edit.maaCultivateSkillLevel', { level: savedLevel }) : '',
    overLimit: savedLevel > maxLevel,
    label: t('edit.maaCultivateGoalSkill'),
    current: currentTextOf(prog, 'skill', ''),
    currentUnknown: unknown,
    state: saved
      ? (goalStateBadge(saved.state) ?? (achieved ? GOAL_STATE_BADGE.achieved : null))
      : null,
    disabled: editorLoading.value || !sklandBound.value || achieved,
    achieved,
    maxed: !unknown && current !== null && maxLevel > 1 && current >= maxLevel,
  }
}

const goalGridsOf = (row: CultivateTargetRow) => {
  const skill = skillLineOf(row)
  return [
    { kind: 'skill' as const, lines: skill ? [skill] : [] },
    { kind: 'mastery' as const, lines: itemLinesOf(row, 'mastery') },
    ...(showModules.value ? [{ kind: 'module' as const, lines: itemLinesOf(row, 'module') }] : []),
  ]
    .map(grid => ({ ...grid, lines: grid.lines.filter(line => !line.achieved && !line.maxed) }))
    .filter(grid => grid.lines.length)
}

// 已绑定但本次快照未携带专精/模组观测（森空岛拉取失败降级本地档案）：
// 目标保留、暂停刷取，须明确提示用户，而不是让「当前 ？」默默出现
const sklandDegraded = computed(
  () =>
    sklandBound.value &&
    rows.value.some(row =>
      (['skill', 'mastery', 'module'] as const).some(
        kind =>
          goalsOf(row, kind).length > 0 && dimensionUnknownOf(progressionOf(row.operatorId), kind)
      )
    )
)

// 目标行变化 → 防抖后请求需求预览（竞态守卫在父级加载器里）。
watch(rows, (nextRows, _previousRows, onCleanup) => {
  const previewTimer = window.setTimeout(() => {
    if (!nextRows.length) return
    props.loadCultivatePreview(serializeCultivateTargets(nextRows))
  }, 600)
  onCleanup(() => window.clearTimeout(previewTimer))
})

onMounted(() => {
  void props.loadCultivatePreview(serializeCultivateTargets(rows.value))
  if (sklandBound.value) void props.loadSklandRoleOptions()
})

const { getPopupContainer, listHeight: popupListHeight } = usePlanSelectPopup()
</script>

<style scoped>
.cultivate-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 24px;
  padding-bottom: 8px;
}
.cultivate-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cultivate-account {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 260px;
}
.cultivate-account-label {
  flex-shrink: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
.cultivate-account .ant-select {
  width: 220px;
  min-width: 0;
  max-width: 100%;
}
.cultivate-execution-settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 360px;
}
.cultivate-execution-settings .ant-checkbox-wrapper {
  margin-inline-start: 0;
}
.cultivate-execution-settings p {
  margin: 0;
}
.cultivate-settings-button {
  flex-shrink: 0;
}

.cultivate-mastery-hint {
  margin-bottom: 12px;
}

.cultivate-target-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 12px;
}

.cultivate-target-search {
  flex: 1 1 240px;
  min-width: 160px;
  max-width: 320px;
}

.cultivate-module-toggle {
  margin-left: auto;
}

.cultivate-top {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.cultivate-top > .cultivate-picker {
  flex: 1 1 380px;
  min-width: 0;
  margin-bottom: 0;
}

.cultivate-picker-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.cultivate-picker-actions > .ant-select {
  flex: 1 1 180px;
  min-width: 120px;
}

/* 干员选择器单行化：标签在左，控件在右侧展开（默认是上下两行）。
   antd 竖排表单会用更高优先级把行方向写成 column，这里前缀 + 显式 row 压回 */
.cultivate-editor .cultivate-picker :deep(.ant-form-item-row) {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: flex-start;
  gap: 8px;
}

.cultivate-editor .cultivate-picker :deep(.ant-form-item-label) {
  /* 标签按单行控件高度居中，避免导入按钮或提示换行后下沉 */
  display: flex;
  align-items: center;
  min-height: 32px;
  padding: 0;
  /* 固定标签列宽，覆盖 antd 窄屏下的整行占位，让两行控件左边缘对齐 */
  flex: 0 0 96px;
}

.cultivate-editor .cultivate-picker :deep(.ant-form-item-control) {
  flex: 1;
  min-width: 0;
}

.skland-feedback {
  margin-top: 4px;
  font-size: 12px;
}

.skland-error {
  color: var(--ant-color-error);
}

.skland-hint {
  opacity: 0.65;
}

.cultivate-group {
  border: 1px solid var(--ant-color-border-secondary);
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
  /* 对齐复选框、折叠箭头之后的干员名称。 */
  margin: 0 0 0 54px;
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

/* 目标列表：每个目标一行 名称 → 当前 → 超限/状态标签 → 档位选择器（最右）；
   左缩进与标题行的干员名称对齐（勾选框 16 + 箭头 22 + 两个间距 8） */
.goal-list {
  display: flex;
  flex-direction: column;
  margin: 2px 0 0;
  padding-left: 54px;
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

.cultivate-pagination {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 12px;
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
  gap: 8px 16px;
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
</style>
