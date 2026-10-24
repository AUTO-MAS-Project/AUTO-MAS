<template>
  <section class="cultivation-overview" :inert="editorBusy">
    <!-- 设置区：一行一事（标签 / 说明 / 控件），不再横向挤一行 -->
    <div class="overview-settings">
      <div class="setting-row">
        <span class="setting-label">{{ t('maaCopilot.enableTitle') }}</span>
        <span class="setting-desc">{{ t('maaCopilot.enableDesc') }}</span>
        <a-switch
          class="setting-control"
          :aria-label="t('maaCopilot.enableTitle')"
          :checked="enabled"
          :disabled="loading"
          @change="emit('save', 'Task.IfCultivate', $event)"
        />
      </div>
      <div class="setting-row">
        <span class="setting-label">{{ t('edit.maaCultivateSklandTitle') }}</span>
        <span class="setting-desc">{{ t('maaCopilot.bindingDesc') }}</span>
        <div class="setting-control binding-control">
          <a-select
            :aria-label="t('edit.maaCultivateSklandTitle')"
            :value="sklandBoundComposite"
            :options="sklandRoleOptionsWithBound"
            :loading="sklandRoleLoading"
            :placeholder="t('edit.maaCultivateSklandRole')"
            :disabled="loading"
            allow-clear
            @dropdown-visible-change="onRoleDropdownVisible"
            @change="handleSklandRoleChange"
          />
        </div>
      </div>
      <div v-if="sklandRoleError" class="setting-error">{{ sklandRoleError }}</div>
      <!-- 执行设置直接平铺；自动培养的版本与口径说明收在行尾 ? -->
      <div class="setting-row">
        <span class="setting-label">{{ t('maaCopilot.executionSettings') }}</span>
        <div class="setting-control execution-checks">
          <a-checkbox
            :checked="formData?.Task?.CultivateAutoRaise ?? false"
            :disabled="loading"
            @change="emit('save', 'Task.CultivateAutoRaise', $event.target.checked)"
            >{{ t('edit.maaCultivateAutoRaise') }}</a-checkbox
          >
          <a-checkbox
            :checked="formData?.Task?.CultivateSkipDuringActivity ?? false"
            :disabled="loading"
            @change="emit('save', 'Task.CultivateSkipDuringActivity', $event.target.checked)"
            >{{ t('edit.maaCultivateSkipActivity') }}</a-checkbox
          >
          <a-checkbox
            :checked="formData?.Task?.CultivateSkipDuringResourceCollection ?? false"
            :disabled="loading"
            @change="
              emit('save', 'Task.CultivateSkipDuringResourceCollection', $event.target.checked)
            "
            >{{ t('edit.maaCultivateSkipResource') }}</a-checkbox
          >
          <a-tooltip :title="executionHint" :trigger="['hover', 'focus']">
            <button type="button" class="setting-help" :aria-label="executionHint">
              <QuestionCircleOutlined aria-hidden="true" />
            </button>
          </a-tooltip>
        </div>
      </div>
    </div>
    <div class="overview-stats" :class="{ 'overview-stats-paused': !enabled }">
      <a-statistic
        :title="t('maaCopilot.statOperators')"
        :value="statOperators"
        :suffix="t('maaCopilot.statOperatorsUnit')"
      />
      <a-statistic
        :title="t('maaCopilot.statGoals')"
        :value="statGoals"
        :suffix="t('maaCopilot.statGoalsUnit')"
      />
      <a-statistic
        :title="t('maaCopilot.statMaterials')"
        :value="statMaterials"
        :suffix="t('maaCopilot.statMaterialsUnit')"
      />
      <a-statistic
        :title="t('maaCopilot.statSanity')"
        :value="statSanity"
        :suffix="statSanity === '—' ? undefined : t('edit.maaCultivateSanityUnit')"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { CultivatePreviewOut } from '@/api'
import { listGoals, parseCultivateTargets } from './cultivateTargets'

type SelectOption = { label: string; value: string }

const props = defineProps<{
  formData: any
  loading: boolean
  editorBusy: boolean
  enabled: boolean
  sklandBound: boolean
  /** "账号组UUID|游戏uid" 复合绑定值（未绑定为 undefined） */
  sklandBoundComposite: string | undefined
  /** 森空岛绑定下拉：合并所有已配置凭据账号组的角色（决策 37/38） */
  sklandRoleOptions: SelectOption[]
  sklandRoleLoading: boolean
  sklandRoleError: string
  /** 按需加载角色列表（下拉首次展开时触发） */
  loadSklandRoleOptions: () => Promise<void>
  /** 养成需求预览（后端纯计算结果） */
  cultivatePreview: CultivatePreviewOut | null
}>()

const emit = defineEmits<{ save: [key: string, value: unknown] }>()

const { t } = useI18n()

const executionHint = computed(() =>
  [t('edit.maaCultivateAutoRaiseHint'), t('edit.maaCultivateAutoRaiseVersionHint')].join('\n')
)

// ── 森空岛绑定 ──
const sklandRoleOptionsWithBound = computed(() => {
  const bound = props.sklandBoundComposite
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
onMounted(() => {
  if (props.sklandBound) void props.loadSklandRoleOptions()
})

// ── 总览统计 ──
const statRows = computed(() => parseCultivateTargets(props.formData?.Task?.CultivateTargets))
const statOperators = computed(() => statRows.value.length)
const statGoals = computed(() =>
  statRows.value.reduce(
    (count, row) =>
      count +
      (['elite', 'skill', 'mastery', 'module'] as const).reduce(
        (sum, kind) =>
          sum + listGoals(row.rawGoals, kind).filter(goal => goal.state !== 'achieved').length,
        0
      ),
    0
  )
)
const statMaterials = computed(() => props.cultivatePreview?.demands.length ?? 0)
const statSanity = computed(() => props.cultivatePreview?.totalExpectedSanity ?? '—')
</script>

<style scoped>
.cultivation-overview {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 8px 24px 16px;
  margin-bottom: 16px;
}

/* ── 设置行：标签 / 说明 / 控件 三段，一行一事 ── */
.setting-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  padding: 14px 0;
}

.setting-row + .setting-row,
.setting-error + .setting-row {
  border-top: 1px solid var(--ant-color-border-secondary);
}

.setting-label {
  flex: 0 0 88px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.setting-desc {
  flex: 1;
  min-width: 200px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.setting-control {
  flex-shrink: 0;
  margin-left: auto;
}

.binding-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.binding-control .ant-select {
  width: 220px;
}

.setting-error {
  padding: 4px 0 8px 104px;
  font-size: 12px;
  color: var(--ant-color-error);
}

.execution-checks {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 24px;
}

.execution-checks .ant-checkbox-wrapper {
  margin-inline-start: 0;
}

/* 行尾 ? 说明按钮（可聚焦，对齐 PipelineRow 的 row-help 口径） */
.setting-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}

.setting-help:hover {
  color: var(--ant-color-primary);
}

.setting-help:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 1px;
}

.overview-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 48px;
  margin-top: 4px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.overview-stats-paused {
  opacity: 0.55;
}

.overview-stats :deep(.ant-statistic-title) {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.overview-stats :deep(.ant-statistic-content) {
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}

.overview-stats :deep(.ant-statistic-content-suffix) {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

@media (max-width: 768px) {
  .overview-stats {
    gap: 12px 24px;
  }

  .setting-error {
    padding-left: 0;
  }
}
</style>
