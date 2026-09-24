<template>
  <!-- 目录不可用/未就绪的提示放在两栏之上：只挂在左栏会让右栏只剩标题，
       看不出为什么是空的 -->
  <a-alert
    v-if="catalogError"
    type="warning"
    :message="catalogError"
    show-icon
    class="catalog-alert"
  />
  <a-spin v-else-if="catalogLoading" :delay="200" class="catalog-spin" />

  <a-row :gutter="24">
    <!-- 左列：任务配置 + 一条龙流程 -->
    <a-col :xs="24" :lg="10">
      <!-- 任务配置：任务级流程开关（沿用 MAA 任务行的形制：开关在左 + 名称 + 细分割线） -->
      <div class="form-section">
        <div class="section-header">
          <h3>{{ t('edit.whimboxTaskSection') }}</h3>
        </div>
        <div class="task-list">
          <div class="task-row" :class="{ 'is-off': !runAllAccounts }">
            <span class="task-toggle">
              <a-switch
                :checked="runAllAccounts"
                :disabled="loading"
                :aria-label="t('edit.whimboxRunAllAccounts')"
                @change="(v: unknown) => emit('save', 'OneDragon.IfRunAllAccounts', v === true)"
              />
            </span>
            <span class="task-name">{{ t('edit.whimboxRunAllAccounts') }}</span>
            <a-tooltip :title="t('edit.whimboxRunAllAccountsHint')">
              <QuestionCircleOutlined class="help-icon task-help" />
            </a-tooltip>
          </div>
        </div>
      </div>

      <!-- 一条龙流程（目录驱动：步骤开关，字段定义由后端从上游三件套下发） -->
      <div class="form-section" style="margin-bottom: 0">
        <div class="section-header">
          <h3>
            {{ t('edit.whimboxOneDragonSection') }}
            <a-tag v-if="upstreamVersion" color="blue" class="version-tag">
              v{{ upstreamVersion }}
            </a-tag>
          </h3>
        </div>

        <template v-if="catalogReady">
          <div class="config-pane">
            <div class="config-pane-header">
              <span class="config-pane-title">{{ t('edit.whimboxFlowNodes') }}</span>
              <a-tag color="default" class="config-pane-count">{{ steps.length }}</a-tag>
            </div>
            <div v-if="steps.length" class="task-list">
              <div
                v-for="(step, index) in steps"
                :key="step.key"
                class="task-row"
                :class="{ 'is-off': !(tasks[step.key] ?? true) }"
              >
                <span class="task-toggle">
                  <a-switch
                    :checked="tasks[step.key] ?? true"
                    :disabled="loading"
                    :aria-label="step.display"
                    @change="(v: unknown) => toggleTask(step.key, v === true)"
                  />
                </span>
                <span class="task-index">{{ index + 1 }}</span>
                <span class="task-name" :title="step.display">{{ step.display }}</span>
              </div>
            </div>
            <a-empty v-else :description="t('edit.whimboxStepsEmpty')" class="config-pane-empty" />
          </div>
          <a-typography-text type="secondary" class="catalog-hint">
            {{ t('edit.whimboxStepHint') }}
          </a-typography-text>
        </template>
      </div>
    </a-col>

    <!-- 右列：高级参数（按 key 前缀成行平铺，同一前缀的项排在同一行） -->
    <a-col :xs="24" :lg="14">
      <div class="form-section" style="margin-bottom: 0">
        <div class="section-header">
          <h3>
            {{ t('edit.whimboxOptionsSection') }}
            <!-- 计数只在目录就绪时渲染：加载中/失败时显示 0 会被读成「上游没有这些字段」 -->
            <a-tag v-if="catalogReady" color="default" class="version-tag">
              {{ options.length }}
            </a-tag>
          </h3>
        </div>
        <template v-if="catalogReady">
          <div class="config-pane config-pane-options">
            <div v-if="options.length" class="option-groups">
              <div v-for="group in optionGroups" :key="group.prefix" class="option-group-row">
                <a-form-item
                  v-for="opt in group.items"
                  :key="opt.key"
                  class="option-tile"
                  :class="`option-tile-${opt.field_type}`"
                >
                  <template #label>
                    <span class="form-label" :title="opt.display">
                      {{ opt.display }}
                    </span>
                  </template>

                  <a-switch
                    v-if="opt.field_type === 'bool'"
                    :checked="optionState[opt.key] ?? opt.default === true"
                    :disabled="loading"
                    @change="(v: unknown) => changeOption(opt.key, v === true)"
                  />

                  <a-input-number
                    v-else-if="opt.field_type === 'int'"
                    :value="
                      (optionState[opt.key] as number | undefined) ??
                      (opt.default as number | undefined)
                    "
                    :disabled="loading"
                    style="width: 100%"
                    @change="(v: unknown) => changeOption(opt.key, v)"
                  />

                  <a-select
                    v-else-if="opt.field_type === 'select'"
                    :value="
                      (optionState[opt.key] as string | undefined) ??
                      (opt.default as string | undefined)
                    "
                    :options="(opt.options ?? []).map(v => ({ value: v, label: v }))"
                    :disabled="loading"
                    :show-search="(opt.options ?? []).length > 8"
                    option-filter-prop="label"
                    size="large"
                    style="width: 100%"
                    allow-clear
                    :placeholder="t('edit.whimboxSelectPlaceholder')"
                    @change="(v: unknown) => changeOption(opt.key, v)"
                  />

                  <a-select
                    v-else-if="opt.field_type === 'multi_select'"
                    :value="
                      (optionState[opt.key] as string[] | undefined) ??
                      (opt.default as string[] | undefined) ??
                      []
                    "
                    :options="(opt.options ?? []).map(v => ({ value: v, label: v }))"
                    :disabled="loading"
                    mode="multiple"
                    size="large"
                    style="width: 100%"
                    :placeholder="t('edit.whimboxMultiSelectPlaceholder')"
                    @change="(v: unknown) => changeOption(opt.key, v as string[])"
                  />

                  <a-input
                    v-else
                    :value="
                      (optionState[opt.key] as string | undefined) ??
                      (opt.default as string | undefined)
                    "
                    :disabled="loading"
                    size="large"
                    class="modern-input"
                    :placeholder="t('edit.whimboxTextPlaceholder')"
                    @blur="
                      commitTextOption(opt, ($event?.target as HTMLInputElement | undefined)?.value)
                    "
                  />
                </a-form-item>
              </div>
            </div>
            <a-empty
              v-else
              :description="t('edit.whimboxOptionsEmpty')"
              class="config-pane-empty"
            />
          </div>
        </template>
      </div>
    </a-col>
  </a-row>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { WhimboxOptionCatalogItem, WhimboxTaskCatalogItem } from '@/api'

const { t } = useI18n()

const props = defineProps<{
  loading: boolean
  steps: WhimboxTaskCatalogItem[]
  options: WhimboxOptionCatalogItem[]
  upstreamVersion: string
  catalogError: string | null
  catalogLoading: boolean
  runAllAccounts: boolean
  tasks: Record<string, boolean>
  optionState: Record<string, unknown>
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
  tasksChange: [tasks: Record<string, boolean>]
  optionsChange: [options: Record<string, unknown>]
}>()

// 目录就绪 = 已拉到且没报错。加载中（含页面初始化、尚未发起拉取那一段）与失败都不渲染
// 数据区，否则「0 个步骤 / 0 个参数」会被读成上游没有这些字段
const catalogReady = computed(() => !props.catalogLoading && !props.catalogError)

/**
 * 目标/参数的成行前缀：取 key 首个下划线前的 token。
 *
 * 上游 OneDragon 节是扁平的、无分组元数据，这层前缀仅用于「同前缀排同一行」的
 * 平铺展示（纯视觉，不写回上游、不参与判定）。`get_` 是上游的动词前缀
 * （get_mira_crown_award），归一为其后的 token，使它与 mira_crown_award_target
 * 同属一行；不做逐键的人工映射表（避免在上游私有格式之上自建语义模型）。
 */
const optionPrefix = (key: string): string => {
  const parts = key.split('_')
  if (parts.length > 1 && parts[0] === 'get') parts.shift()
  return parts[0] ?? key
}

// 按前缀把参数分组（同一前缀必合并为一行、定位在它首次出现的位置，组内保持上游相对
// 顺序）：合并只做展示分组，不写回上游
const optionGroups = computed<Array<{ prefix: string; items: WhimboxOptionCatalogItem[] }>>(() => {
  const groups = new Map<string, WhimboxOptionCatalogItem[]>()
  for (const opt of props.options) {
    const prefix = optionPrefix(opt.key)
    const items = groups.get(prefix)
    if (items) {
      items.push(opt)
    } else {
      groups.set(prefix, [opt])
    }
  }
  return [...groups].map(([prefix, items]) => ({ prefix, items }))
})

// 覆盖集以整张 map 为最小保存单元（单键粒度无意义），变更时上抛新 map
const toggleTask = (key: string, value: boolean) => {
  emit('tasksChange', { ...props.tasks, [key]: value })
}

// 清空（null/undefined）语义 = 取消该项覆盖：删键而非写 null。写 null 会透传进
// 上游 config.json，而界面按 `?? opt.default` 又回落显示模板默认值，界面与落盘不一致。
// 多选全删是显式空集覆盖（`[]` 会如实落盘、界面也如实显示空），不在此列。
const changeOption = (key: string, value: unknown) => {
  const next = { ...props.optionState }
  if (value === null || value === undefined) {
    delete next[key]
  } else {
    next[key] = value
  }
  emit('optionsChange', next)
}

// 文本框没有独立的变更时机，用 blur 提交：与当前生效值相同时不写覆盖（焦点进出不该
// 把显示中的模板默认值钉成覆盖项），清空按「取消覆盖」删键，与单值控件同口径
const commitTextOption = (opt: WhimboxOptionCatalogItem, raw: unknown) => {
  const resolved =
    (props.optionState[opt.key] as string | undefined) ?? (opt.default as string | undefined) ?? ''
  const next = typeof raw === 'string' ? raw : ''
  if (next === resolved) return
  changeOption(opt.key, next === '' ? null : next)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.version-tag {
  font-weight: 600;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.catalog-alert {
  margin-bottom: 16px;
}

.catalog-spin {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

/* 任务行：照 MAA 任务行（PipelineRow）的形制——开关在左、无卡片边框、
   行间细分割线、默认尺寸开关、名称为 15px/600、关闭态名称转次级色 */
.task-list {
  display: flex;
  flex-direction: column;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 52px;
  padding: 6px 4px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.task-row:last-child {
  border-bottom: none;
}

/* 固定槽位宽度（默认尺寸开关 44px），与其他开关行保持名称左边界一致 */
.task-toggle {
  flex: 0 0 44px;
  display: flex;
  align-items: center;
}

/* 流程节点序号：体现上游步骤的执行顺序 */
.task-index {
  flex: 0 0 auto;
  min-width: 20px;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text-tertiary);
  text-align: right;
}

.task-name {
  flex: 0 0 auto;
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.task-row.is-off .task-name {
  color: var(--ant-color-text-secondary);
}

.task-help {
  margin-left: -6px;
  font-size: 13px;
}

.catalog-hint {
  display: block;
  margin-top: 8px;
  font-size: 12px;
}

/* 左右两栏：左=流程（任务配置 + 一条龙流程），右=高级参数。左栏步骤数有限，
   超长时独立滚动；右栏参数行多得多，**不限高**、随内容展开交给页面滚动
   （限高会把后半段参数藏进小滚动条，列表被截得看不出还有多少项）。 */
.config-pane {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 560px;
  overflow-y: auto;
  padding-right: 8px;
  padding-bottom: 8px;
}

/* 右栏参数不限高：随内容展开，由页面滚动 */
.config-pane-options {
  max-height: none;
  overflow-y: visible;
}

.config-pane-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px 8px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.config-pane-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.config-pane-count {
  font-weight: 600;
}

.config-pane-empty {
  padding: 16px 0;
}

.option-groups {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-group-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 20px;
}

/* margin-bottom 必须 !important：实测去掉后 Ant 的 .ant-form-item 默认 24px 生效
   （computed 由 12px 变 24px），瓦片行内间距会被撑开 */
.option-tile {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 100%;
  margin-bottom: 12px !important;
}

/* 瓦片按控件类型给最小宽度：标签过长时瓦片随标签自然变宽，不裁切描述 */
.option-tile-bool {
  min-width: 220px;
}

.option-tile-int {
  min-width: 180px;
}

.option-tile-select {
  min-width: 240px;
}

.option-tile-text {
  min-width: 240px;
}

.option-tile-multi_select {
  min-width: 340px;
}

/* 控件宽度跟随瓦片，但不超过一个舒适上限（多选用更宽上限容纳标签） */
.option-tile :deep(.ant-form-item-control) {
  max-width: 320px;
}

.option-tile-multi_select :deep(.ant-form-item-control) {
  max-width: 420px;
}

.option-tile-bool :deep(.ant-form-item-control),
.option-tile-int :deep(.ant-form-item-control) {
  max-width: none;
}
</style>
