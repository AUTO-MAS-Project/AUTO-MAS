<template>
  <div v-if="task" class="module-panel">
    <div class="panel-header">
      <div class="panel-title-line">
        <span class="panel-title">{{ task.name }}</span>
        <a-tag>{{ phaseLabel }}</a-tag>
        <!-- 两个引擎都能选时下面有分段控件；只有一个时在这里标出是谁的设置 -->
        <a-tag v-if="!showEngineSwitch && engine" :color="engineColor" class="panel-engine">
          {{ engineName }}
        </a-tag>
      </div>
      <div v-if="task.description" class="panel-meta">{{ task.description }}</div>
    </div>

    <!-- 自己包一层竖排表单：面板里的表单项不挂到页面表单的模型上，且固定上标签下控件 -->
    <a-form layout="vertical">
      <a-form-item v-if="showEngineSwitch" :label="t('edit.engine')" class="engine-item">
        <a-segmented
          :value="engine"
          :options="engineOptions"
          :disabled="saving"
          block
          @change="handleEngineChange"
        />
      </a-form-item>

      <!-- 模块专属的设置（体力模块的刷取副本与历战余响）由页面通过插槽放进来 -->
      <slot name="extra" />

      <!-- 表单提示与失效覆盖合成一条，可展开看明细 -->
      <a-alert v-if="noticeCount" type="warning" show-icon class="panel-alert">
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

    <div class="panel-footer">
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
    </div>
  </div>
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
  task: HSRManagedTask | null
  engine?: HSREngine
  form?: HSRManagedEngineForm
  engineOptions: { value: HSREngine; label: string }[]
  /** 引擎显示名（三月七 / SRA）。 */
  engineName: string
  engineColor: string
  saving: boolean
  loading: boolean
  shared?: boolean
  cloud?: boolean
}>()

const emit = defineEmits<{
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

// 云·星穹铁道恒由三月七执行；客户端只有真有两个可选引擎时才给分段控件
const showEngineSwitch = computed(() => !props.cloud && props.engineOptions.length > 1)

const phaseLabel = computed(() =>
  props.task?.phase === 'weekly' ? t('edit.weekly') : t('edit.daily')
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
</script>

<style scoped>
.module-panel {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.panel-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.panel-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-title-line :deep(.ant-tag) {
  margin-inline-end: 0;
}

.panel-title {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 700;
}

.panel-engine {
  margin-left: auto;
}

.panel-meta {
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.engine-item {
  margin-bottom: 16px;
}

.panel-alert {
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

.panel-footer {
  margin-top: 20px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.module-reset {
  padding-inline: 0;
}
</style>
