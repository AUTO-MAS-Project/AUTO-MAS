<template>
  <a-form-item class="config-mode-form-item">
    <template #label>
      <span class="config-mode-label">
        {{ t('core.edit.configurationManagement') }}
        <span v-if="saving" class="config-mode-saving">
          <LoadingOutlined spin />
          {{ t('core.edit.saving') }}
        </span>
      </span>
    </template>

    <ConfigModeOptions
      :model-value="modelValue"
      :disabled="disabled || saving"
      :options="sourceOptions"
      :label="t('core.edit.configurationManagement')"
      @change="handleChange"
    />

    <!-- 调用方显式传空串表示卡片描述已够用、不挂来源提示（HSR）；不传仍用默认文案 -->
    <a-alert
      v-if="alertMessage"
      class="config-mode-alert"
      type="info"
      show-icon
      :message="alertMessage"
    />

    <!--
      覆写常规配置（overlay 层）：账号级开关，两者合起来就是 3×2 的 base ⊕ overlay 子态。
      只有声明了 quickConfig 的调用方才渲染，避免给未接入运行时的专项做出死开关。
      形态与上面的 base 三态卡片同构；BetterGI 的 overlay 由配置来源派生（原生来源 = 关、
      共享 / 独立 = 开），传 quickConfigReadonly 只读展示派生结果，避免出现可点却无效的卡片。
    -->
    <a-form-item v-if="quickConfig !== undefined" class="overlay-config-form-item">
      <template #label>
        <span class="config-mode-label">
          {{ t('core.edit.enableQuickConfiguration') }}
          <a-tooltip :title="t('core.edit.overridesCurrentScriptConfiguration')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <span v-if="quickConfigReadonly" class="config-mode-derived">
            {{ t('core.edit.quickConfigDerivedHint') }}
          </span>
        </span>
      </template>
      <ConfigModeOptions
        :model-value="quickConfig"
        :disabled="overlayDisabled"
        :options="overlayOptions"
        :label="t('core.edit.enableQuickConfiguration')"
        @change="handleOverlayChange"
      />
    </a-form-item>

    <!--
      生效语义：跟着 base × overlay 子态动态变化（3×2 六种组合，文案对齐开发者文档
      developer/config-semantics.html）。未接入 overlay 的专项没有子态可讲，整块不渲染。
    -->
    <div v-if="semantics.formula" class="config-effective" role="status" aria-live="polite">
      <span class="config-effective-title">{{ t('core.edit.configSemanticsTitle') }}</span>
      <p class="config-effective-formula">{{ semantics.formula }}</p>
      <p v-if="semantics.effect" class="config-effective-effect">{{ semantics.effect }}</p>
      <p v-if="semantics.note" class="config-effective-note">{{ semantics.note }}</p>
      <p v-if="showGuiHint && semantics.gui" class="config-effective-gui">{{ semantics.gui }}</p>
    </div>
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { LoadingOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
import { composeConfigSemantics } from './configSemantics'
import ConfigModeOptions from './ConfigModeOptions.vue'
import type { ConfigModeOption } from './configModeOptions'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    modelValue: boolean | string
    disabled?: boolean
    saving?: boolean
    options?: ConfigModeOption[]
    alertMessage?: string
    /**
     * 快速配置开关（用户级，独立于 Info.Base）。
     * 未传入表示调用方未接入该字段，此时不渲染，避免做出无运行时的死开关。
     * 必须显式 default: undefined：Boolean prop 未声明 default 时 Vue 会
     * casting 成 false，「不传」与「显式传 false」无法区分，守卫
     * v-if="quickConfig !== undefined" 将永远通过（#781 移除绑定后的真实事故）。
     */
    quickConfig?: boolean | undefined
    quickConfigDisabled?: boolean
    /** overlay 值由配置来源派生（BetterGI）：只读展示，卡片置灰且接不到变更 */
    quickConfigReadonly?: boolean | undefined
    /**
     * 是否在语义面板里渲染「界面入口」说明（gui）。
     * 调用方已有自己的「配置操作」块、把这句话放到操作按钮下方时传 false，
     * 免得同一句既挂在配置来源下、又挂在配置操作下，反而看不清「选什么就改什么」。
     */
    showGuiHint?: boolean
  }>(),
  {
    options: undefined,
    alertMessage: undefined,
    quickConfig: undefined,
    quickConfigDisabled: undefined,
    quickConfigReadonly: undefined,
    showGuiHint: true,
  }
)

// 默认值不能写在 withDefaults 里：defineProps 会被提升到 setup() 之外，
// 引用不到 useI18n() 返回的 t，编译期直接报错（typecheck 与单测都发现不了，
// 只有真正构建时才暴露）。改成在这里按需兜底。
const defaultOptions = computed<ConfigModeOption[]>(() => [
  {
    value: true,
    title: t('core.edit.perUserConfiguration'),
    description: t('core.edit.saveSeparateConfigurationThis'),
    icon: 'database',
  },
  {
    value: false,
    title: t('core.edit.scriptDirectConfiguration'),
    description: t('core.edit.useScriptSCurrent'),
    icon: 'file',
  },
])

const options = computed(() => props.options ?? defaultOptions.value)
const alertMessage = computed(() => props.alertMessage ?? t('core.edit.configSourceHint'))

const sourceOptions = computed(() => {
  const independent = t('core.edit.configModeSummaryIndependent')
  const native = t('core.edit.configModeSummaryNative')
  const summaries: Record<string, string> = {
    shared: t('core.edit.configModeSummaryShared'),
    independent,
    native,
    true: independent,
    false: native,
  }
  return options.value.map(option => ({
    ...option,
    summary: option.summary ?? summaries[String(option.value)],
  }))
})

/** overlay 的两态卡片，与 base 的三态卡片同构（同一套样式类） */
const overlayOptions = computed(() => [
  {
    value: true,
    title: t('core.edit.overlayConfigEnabled'),
    summary: t('core.edit.configModeSummaryOverlayEnabled'),
    description: t('core.edit.overlayConfigEnabledDesc'),
    icon: 'setting' as const,
  },
  {
    value: false,
    title: t('core.edit.overlayConfigDisabled'),
    summary: t('core.edit.configModeSummaryOverlayDisabled'),
    description: t('core.edit.overlayConfigDisabledDesc'),
    icon: 'file' as const,
  },
])

const overlayDisabled = computed(
  () =>
    props.disabled === true ||
    props.saving === true ||
    props.quickConfigDisabled === true ||
    props.quickConfigReadonly === true
)

/** 当前 base × overlay 子态的生效语义（公式 + 说明 + 界面入口），未接入 overlay 的专项为空 */
const semantics = computed(() => composeConfigSemantics(props.modelValue, props.quickConfig, t))

const emit = defineEmits<{
  change: [value: boolean | string]
  quickConfigChange: [value: boolean]
}>()

const handleChange = (event: RadioChangeEvent) => {
  emit('change', event.target.value as boolean | string)
}

const handleOverlayChange = (event: RadioChangeEvent) => {
  emit('quickConfigChange', event.target.value as boolean)
}
</script>

<style scoped>
.config-mode-form-item {
  margin-top: 8px;
}

.config-mode-label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  font-weight: 600;
}

.config-mode-saving {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 400;
}

.config-mode-derived {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 400;
}

.config-mode-alert {
  margin-top: 12px;
}

.overlay-config-form-item {
  margin-top: 16px;
}

/* 生效语义面板：与上面的来源提示区分开，作为当前子态的结果呈现 */
.config-effective {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 12px;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-left: 4px solid var(--ant-color-primary);
  border-radius: 8px;
  background: var(--ant-color-bg-layout);
}

.config-effective-title {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.config-effective-formula {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}

/* 改动范围：一句话点明这次任务改的是哪一份配置，比下面的细节行更重，便于一眼扫到重点 */
.config-effective-effect {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

.config-effective-note {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

/* 界面入口说明：打开脚本自带界面改的是哪一份配置，随 base 来源变化 */
.config-effective-gui {
  margin: 4px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}
</style>
