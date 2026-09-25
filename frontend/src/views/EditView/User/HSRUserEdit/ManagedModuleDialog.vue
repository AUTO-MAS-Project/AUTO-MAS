<template>
  <a-modal
    :open="open"
    width="720px"
    class="hsr-module-dialog"
    :body-style="{ maxHeight: '70vh', overflowY: 'auto', overflowX: 'hidden' }"
    @cancel="close"
  >
    <template #title>
      <div v-if="task" class="dialog-title">
        <span>{{ task.name }}</span>
        <a-tag>{{ phaseLabel }}</a-tag>
        <a-tooltip v-if="!enabled" :title="notEnabledTip">
          <a-tag class="not-enabled-tag">{{ t('edit.hsrTaskNotEnabled') }}</a-tag>
        </a-tooltip>
      </div>
    </template>

    <!-- 自己包一层竖排表单：弹窗里的表单项不挂到页面表单的模型上，且固定上标签下控件 -->
    <a-form v-if="task" layout="vertical">
      <div v-if="task.description" class="task-description">{{ task.description }}</div>

      <!-- 执行引擎：云·星穹铁道恒由三月七执行；客户端只有真有两个可选引擎时才给分段控件 -->
      <a-typography-text
        v-if="cloud"
        type="secondary"
        class="engine-only-line"
        data-testid="hsr-cloud-engine-line"
      >
        {{ t('edit.hsrCloudRunByM7a') }}
      </a-typography-text>
      <a-form-item
        v-else-if="engineOptions.length > 1"
        :label="t('edit.engine')"
        :extra="shared ? t('edit.hsrSharedEngineSwitchHint') : t('edit.hsrEngineSwitchHint')"
        class="engine-item"
      >
        <a-segmented
          :value="engine"
          :options="engineOptions"
          :disabled="saving"
          block
          @change="handleEngineChange"
        />
      </a-form-item>
      <a-typography-text v-else-if="engine" type="secondary" class="engine-only-line">
        <a-tooltip :title="sourceTip">
          {{ t('edit.hsrRunByEngine', { engine: engineName }) }}
        </a-tooltip>
      </a-typography-text>

      <!-- 模块专属的设置（体力模块的刷取副本与历战余响）由页面通过插槽放进来 -->
      <slot name="extra" />

      <!-- 表单提示与失效覆盖合成一条，可展开看明细 -->
      <a-alert v-if="noticeCount" type="warning" show-icon class="dialog-alert">
        <template #message>
          <span>{{ noticeHeadline }}</span>
          <a-button
            v-if="noticeHasDetails"
            type="link"
            size="small"
            class="notice-toggle"
            @click="noticeExpanded = !noticeExpanded"
          >
            {{ noticeExpanded ? t('edit.hsrNoticeCollapse') : t('edit.hsrNoticeExpand') }}
          </a-button>
        </template>
        <template v-if="noticeHasDetails && noticeExpanded" #description>
          <ul v-if="warnings.length > (droppedOverrides.length ? 0 : 1)" class="notice-list">
            <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
          </ul>
          <template v-if="droppedOverrides.length">
            <div v-if="warnings.length" class="notice-subtitle">
              {{ t('edit.invalidManagedOverridesTitle', { n: droppedOverrides.length }) }}
            </div>
            <ul class="notice-list">
              <li v-for="item in droppedOverrides" :key="item.key">
                <span class="dropped-name">{{ droppedLabel(item.key) }}</span>
                <span>{{ droppedReasonLabel(item.reason) }}</span>
                <span class="dropped-value">
                  {{
                    t('edit.invalidManagedOverrideSaved', {
                      value: formatOverrideValue(item.value),
                    })
                  }}
                </span>
              </li>
            </ul>
            <a-popconfirm
              :overlay-style="{ maxWidth: '360px' }"
              :title="t('edit.clearInvalidManagedOverridesConfirm', { n: droppedOverrides.length })"
              :ok-text="t('edit.ok')"
              :cancel-text="t('edit.cancel')"
              ok-type="danger"
              :disabled="saving"
              @confirm="
                emit(
                  'clearInvalid',
                  droppedOverrides.map(item => item.key)
                )
              "
            >
              <a-button size="small" danger :disabled="saving">
                {{ t('edit.clearInvalidManagedOverrides') }}
              </a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-alert>

      <template v-if="form">
        <a-empty v-if="!form.fields.length" :description="t('edit.thisVersionHasNothing')" />
        <template v-else>
          <DynamicManagedFields
            v-if="layout.common.length"
            :fields="layout.common"
            :disabled="saving"
            @change="handleFieldChange"
            @reset="handleFieldReset"
          />
          <a-collapse
            v-if="layout.groups.length"
            v-model:active-key="activeGroupKeys"
            class="group-collapse"
            :bordered="false"
          >
            <a-collapse-panel v-for="group in layout.groups" :key="group.key">
              <template #header>
                <span class="group-header">
                  <span>{{ groupLabel(group.key) }}</span>
                  <span v-if="group.overriddenCount" class="group-overridden">
                    {{ t('edit.hsrGroupOverriddenCount', { n: group.overriddenCount }) }}
                  </span>
                </span>
              </template>
              <DynamicManagedFields
                :fields="group.fields"
                :disabled="saving"
                @change="handleFieldChange"
                @reset="handleFieldReset"
              />
            </a-collapse-panel>
          </a-collapse>
        </template>
      </template>
      <a-empty v-else :description="t('edit.engineReturnedNoDynamic')" />
    </a-form>

    <!-- 底栏放在弹窗 footer 里：正文滚动时「完成」与模块恢复始终可见 -->
    <template #footer>
      <div v-if="task" class="dialog-footer">
        <a-popconfirm
          :overlay-style="{ maxWidth: '360px' }"
          :title="t('edit.hsrModuleResetConfirmTitle', { engine: engineName })"
          :description="
            shared ? t('edit.hsrModuleResetConfirmShared') : t('edit.hsrModuleResetConfirmUser')
          "
          :ok-text="t('edit.ok')"
          :cancel-text="t('edit.cancel')"
          :disabled="loading || saving || !form"
          @confirm="emit('resetModule')"
        >
          <a-button type="link" size="small" class="module-reset" :disabled="saving || !form">
            {{ t('edit.hsrModuleReset', { engine: engineName }) }}
          </a-button>
        </a-popconfirm>
        <a-button type="primary" @click="close">{{ t('edit.hsrDialogDone') }}</a-button>
      </div>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getHSRDroppedOverrides,
  type HSRDroppedOverrideReason,
  type HSREngine,
  type HSRManagedEngineForm,
  type HSRManagedTask,
} from '@/composables/useHSRPluginApi'
import DynamicManagedFields from './DynamicManagedFields.vue'
import { splitFieldsByGroup } from './managedFields'

const { t, te } = useI18n()

const props = defineProps<{
  open: boolean
  task: HSRManagedTask | null
  engine?: HSREngine
  form?: HSRManagedEngineForm
  engineOptions: { value: HSREngine; label: string }[]
  /** 引擎显示名（三月七 / SRA）。 */
  engineName: string
  enabled: boolean
  saving: boolean
  loading: boolean
  shared?: boolean
  cloud?: boolean
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  engineChange: [engine: HSREngine]
  fieldChange: [key: string, value: unknown]
  fieldReset: [key: string]
  /** 只清当前引擎当前模块在 MAS 里的覆盖值。 */
  resetModule: []
  clearInvalid: [keys: string[]]
}>()

const activeGroupKeys = ref<string[]>([])
const noticeExpanded = ref(false)

// 换了模块或引擎：折叠面板回到全收起
watch(
  // 用字符串比较：快照重拉后 task 是新对象，但模块和引擎没变时不该收起
  () => `${props.task?.key ?? ''}|${props.engine ?? ''}`,
  () => {
    activeGroupKeys.value = []
    noticeExpanded.value = false
  }
)

const phaseLabel = computed(() =>
  props.task?.phase === 'weekly' ? t('edit.weekly') : t('edit.daily')
)

const notEnabledTip = computed(() =>
  props.shared ? t('edit.hsrSharedModuleNotEnabled') : t('edit.thisModuleNotEnabled')
)

const sourceTip = computed(() =>
  props.form?.source ? t('edit.hsrReadFrom', { source: props.form.source }) : undefined
)

const layout = computed(() => splitFieldsByGroup(props.form?.fields ?? []))

const groupLabel = (group: string) =>
  te(`edit.hsrFieldGroup.${group}`)
    ? t(`edit.hsrFieldGroup.${group}`)
    : t('edit.hsrFieldGroup.misc')

const warnings = computed(() => props.form?.warnings ?? [])
const droppedOverrides = computed(() => getHSRDroppedOverrides(props.form))
const noticeCount = computed(() => warnings.value.length + (droppedOverrides.value.length ? 1 : 0))
// 只有一条表单提示时直接显示它；有失效覆盖或多条时显示概括，明细折叠
const noticeHasDetails = computed(
  () => droppedOverrides.value.length > 0 || warnings.value.length > 1
)
const noticeHeadline = computed(() => {
  if (!noticeHasDetails.value) return warnings.value[0] ?? ''
  if (!warnings.value.length) {
    return t('edit.invalidManagedOverridesTitle', { n: droppedOverrides.value.length })
  }
  return t('edit.hsrModuleNotices', { n: noticeCount.value })
})

// 失效覆盖尽量显示字段名；当前表单里已经没有这个字段时只能显示原始键
const droppedLabel = (key: string) =>
  props.form?.fields.find(field => field.key === key)?.label ?? key

const droppedReasonLabel = (reason: HSRDroppedOverrideReason) =>
  reason === 'type' ? t('edit.invalidManagedOverrideType') : t('edit.invalidManagedOverrideUnknown')

const formatOverrideValue = (value: unknown) =>
  typeof value === 'string' ? value : JSON.stringify(value)

const handleEngineChange = (value: string | number) => {
  if (value !== 'SRA' && value !== 'M7A') return
  emit('engineChange', value)
}

const handleFieldChange = (key: string, value: unknown) => emit('fieldChange', key, value)
const handleFieldReset = (key: string) => emit('fieldReset', key)

// 关闭前先让正在输入的文本框失焦：失焦即提交，关掉弹窗不丢刚打的字
const close = () => {
  const active = document.activeElement
  if (active instanceof HTMLElement) active.blur()
  emit('update:open', false)
}
</script>

<style scoped>
.dialog-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.not-enabled-tag {
  color: var(--ant-color-text-tertiary);
}

.task-description {
  margin-bottom: 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.engine-item {
  margin-bottom: 16px;
}

.engine-only-line {
  display: block;
  margin-bottom: 16px;
  font-size: 13px;
}

.dialog-alert {
  margin-bottom: 16px;
}

.notice-toggle {
  height: auto;
  padding: 0 4px;
}

.notice-list {
  margin: 0 0 8px;
  padding-left: 18px;
}

.notice-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.notice-subtitle {
  margin-bottom: 4px;
  font-weight: 600;
}

.dropped-name {
  font-weight: 600;
}

.dropped-value {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.group-collapse {
  margin-top: 16px;
}

.group-header {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.group-overridden {
  color: var(--ant-color-primary);
  font-size: 12px;
  font-weight: 400;
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.module-reset {
  padding-inline: 0;
}
</style>
