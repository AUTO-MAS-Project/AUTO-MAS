<template>
  <a-form-item class="config-mode-form-item">
    <template #label>
      <span class="config-mode-label">
        {{ t('edit.configurationManagement') }}
        <span v-if="saving" class="config-mode-saving">
          <LoadingOutlined spin />
          {{ t('edit.saving') }}
        </span>
      </span>
    </template>

    <a-radio-group
      :value="modelValue"
      :disabled="disabled || saving"
      class="config-mode-options"
      :style="{ gridTemplateColumns: `repeat(${Math.min(options.length, 3)}, minmax(0, 1fr))` }"
      :aria-label="t('edit.configurationManagement')"
      @change="handleChange"
    >
      <a-tooltip
        v-for="option in options"
        :key="String(option.value)"
        :title="option.disabled ? option.disabledReason : undefined"
      >
        <label
          :class="[
            'config-mode-option',
            { selected: modelValue === option.value, disabled: isOptionDisabled(option) },
          ]"
          :aria-disabled="option.disabled || undefined"
        >
          <a-radio
            :value="option.value"
            class="config-mode-radio"
            :disabled="isOptionDisabled(option)"
          />
          <span class="config-mode-icon">
            <DatabaseOutlined v-if="option.icon === 'database'" />
            <SettingOutlined v-else-if="option.icon === 'setting'" />
            <FileTextOutlined v-else />
          </span>
          <span class="config-mode-copy">
            <span class="config-mode-title">{{ option.title }}</span>
            <span class="config-mode-description">{{ option.description }}</span>
          </span>
        </label>
      </a-tooltip>
    </a-radio-group>

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
      形态与上面的 base 三态卡片同构；BetterGI 的 overlay 由配置来源派生（直控 = 关、
      共享 / 独立 = 开），传 quickConfigReadonly 只读展示派生结果，避免出现可点却无效的卡片。
    -->
    <a-form-item v-if="quickConfig !== undefined" class="overlay-config-form-item">
      <template #label>
        <span class="config-mode-label">
          {{ t('edit.enableQuickConfiguration') }}
          <a-tooltip :title="t('edit.overridesCurrentScriptConfiguration')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <span v-if="quickConfigReadonly" class="config-mode-derived">
            {{ t('edit.quickConfigDerivedHint') }}
          </span>
        </span>
      </template>
      <a-radio-group
        :value="quickConfig"
        :disabled="overlayDisabled"
        class="config-mode-options"
        :style="{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }"
        :aria-label="t('edit.enableQuickConfiguration')"
        @change="handleOverlayChange"
      >
        <label
          v-for="option in overlayOptions"
          :key="String(option.value)"
          :class="[
            'config-mode-option',
            { selected: quickConfig === option.value, disabled: overlayDisabled },
          ]"
          :aria-disabled="overlayDisabled || undefined"
        >
          <a-radio :value="option.value" class="config-mode-radio" :disabled="overlayDisabled" />
          <span class="config-mode-icon">
            <SettingOutlined v-if="option.icon === 'setting'" />
            <FileTextOutlined v-else />
          </span>
          <span class="config-mode-copy">
            <span class="config-mode-title">{{ option.title }}</span>
            <span class="config-mode-description">{{ option.description }}</span>
          </span>
        </label>
      </a-radio-group>
    </a-form-item>

    <!--
      生效语义：跟着 base × overlay 子态动态变化（3×2 六种组合，文案对齐开发者文档
      developer/config-semantics.html）。未接入 overlay 的专项没有子态可讲，整块不渲染。
    -->
    <div v-if="semantics.formula" class="config-effective" role="status" aria-live="polite">
      <span class="config-effective-title">{{ t('edit.configSemanticsTitle') }}</span>
      <p class="config-effective-formula">{{ semantics.formula }}</p>
      <p v-if="semantics.note" class="config-effective-note">{{ semantics.note }}</p>
      <p v-if="semantics.gui" class="config-effective-gui">{{ semantics.gui }}</p>
    </div>
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import {
  DatabaseOutlined,
  FileTextOutlined,
  LoadingOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
import { composeConfigSemantics } from './configSemantics'

const { t } = useI18n()

type ConfigModeOption = {
  value: boolean | string
  title: string
  description: string
  icon?: 'database' | 'file' | 'setting'
  /** 该选项不可选（如该专项运行时不存在脚本级共享配置）：置灰且不可勾选 */
  disabled?: boolean
  /** 不可选原因（悬停该选项时的提示文案） */
  disabledReason?: string
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean | string
    disabled?: boolean
    saving?: boolean
    options?: ConfigModeOption[]
    alertMessage?: string
    /**
     * 快速配置开关（用户级，独立于 Info.Mode）。
     * 未传入表示调用方未接入该字段，此时不渲染，避免做出无运行时的死开关。
     * 必须显式 default: undefined：Boolean prop 未声明 default 时 Vue 会
     * casting 成 false，「不传」与「显式传 false」无法区分，守卫
     * v-if="quickConfig !== undefined" 将永远通过（#781 移除绑定后的真实事故）。
     */
    quickConfig?: boolean | undefined
    quickConfigDisabled?: boolean
    /** overlay 值由配置来源派生（BetterGI）：只读展示，卡片置灰且接不到变更 */
    quickConfigReadonly?: boolean | undefined
  }>(),
  {
    options: undefined,
    alertMessage: undefined,
    quickConfig: undefined,
    quickConfigDisabled: undefined,
    quickConfigReadonly: undefined,
  }
)

// 默认值不能写在 withDefaults 里：defineProps 会被提升到 setup() 之外，
// 引用不到 useI18n() 返回的 t，编译期直接报错（typecheck 与单测都发现不了，
// 只有真正构建时才暴露）。改成在这里按需兜底。
const defaultOptions = computed<ConfigModeOption[]>(() => [
  {
    value: true,
    title: t('edit.perUserConfiguration'),
    description: t('edit.saveSeparateConfigurationThis'),
    icon: 'database',
  },
  {
    value: false,
    title: t('edit.scriptDirectConfiguration'),
    description: t('edit.useScriptSCurrent'),
    icon: 'file',
  },
])

const options = computed(() => props.options ?? defaultOptions.value)
const alertMessage = computed(() => props.alertMessage ?? t('edit.configSourceHint'))

/** 整组禁用（页面加载/保存中）或该选项声明 disabled 时，选项置灰不可勾选 */
const isOptionDisabled = (option: ConfigModeOption): boolean =>
  props.disabled === true || props.saving === true || option.disabled === true

/** overlay 的两态卡片，与 base 的三态卡片同构（同一套样式类） */
const overlayOptions = computed(() => [
  {
    value: true,
    title: t('edit.overlayConfigEnabled'),
    description: t('edit.overlayConfigEnabledDesc'),
    icon: 'setting' as const,
  },
  {
    value: false,
    title: t('edit.overlayConfigDisabled'),
    description: t('edit.overlayConfigDisabledDesc'),
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

.config-mode-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
}

.config-mode-option {
  display: grid;
  grid-template-columns: auto 32px minmax(0, 1fr);
  align-items: start;
  gap: 12px;
  min-width: 0;
  min-height: 96px;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    box-shadow 0.2s ease;
}

.config-mode-option:hover:not(.disabled) {
  border-color: var(--ant-color-primary-hover);
}

.config-mode-option.selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 1px var(--ant-color-primary);
}

.config-mode-option.disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.config-mode-radio {
  margin-top: 5px;
}

.config-mode-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--ant-color-bg-layout);
  color: var(--ant-color-text-secondary);
  font-size: 17px;
}

.config-mode-option.selected .config-mode-icon {
  color: var(--ant-color-primary);
}

.config-mode-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.config-mode-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}

.config-mode-description {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
  /* 描述文案可能含 \n 换行（如 ZZZ-OD 直控的约束说明），按原文换行渲染 */
  white-space: pre-line;
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

@media (max-width: 760px) {
  .config-mode-options {
    grid-template-columns: 1fr;
  }
}
</style>
