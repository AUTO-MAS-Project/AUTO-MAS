<template>
  <a-row :gutter="24">
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint :text="t('core.edit.zzzodScreenSize')" variant="form" />
        </template>
        <a-select
          v-model:value="screenSize"
          :options="screenSizeOptions"
          size="large"
          class="modern-select"
          :disabled="disabled"
          @change="emit('save-screen-size', $event)"
        />
      </a-form-item>
    </a-col>
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint :text="t('core.edit.zzzodFullScreen')" variant="form" />
        </template>
        <a-select
          v-model:value="fullScreen"
          :options="fullScreenOptions"
          size="large"
          class="modern-select"
          :disabled="disabled"
          @change="emit('save-full-screen', $event)"
        />
      </a-form-item>
    </a-col>
  </a-row>
  <a-row :gutter="24">
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint :text="t('core.edit.zzzodPopupWindow')" variant="form" />
        </template>
        <a-switch
          v-model:checked="popupWindow"
          :disabled="disabled"
          @change="emit('save-popup-window', $event === true)"
        />
      </a-form-item>
    </a-col>
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint
            :text="t('core.edit.zzzodDx12')"
            :hint="t('core.edit.zzzodDx12Hint')"
            variant="form"
          />
        </template>
        <a-switch
          v-model:checked="dx12"
          :disabled="disabled"
          @change="emit('save-dx12', $event === true)"
        />
      </a-form-item>
    </a-col>
  </a-row>
  <a-row :gutter="24">
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint :text="t('core.edit.zzzodMonitor')" variant="form" />
        </template>
        <a-select
          v-model:value="monitor"
          :options="monitorOptions"
          size="large"
          class="modern-select"
          :disabled="disabled"
          @change="emit('save-monitor', $event)"
        />
      </a-form-item>
    </a-col>
  </a-row>
  <a-row :gutter="24">
    <a-col :span="24">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint :text="t('core.edit.zzzodAdvanceArgs')" variant="form" />
        </template>
        <a-input
          v-model:value="advancedArguments"
          :placeholder="t('core.edit.zzzodAdvanceArgsPlaceholder')"
          size="large"
          class="modern-input"
          :disabled="disabled"
          @blur="emit('save-advanced-arguments', advancedArguments)"
        />
      </a-form-item>
    </a-col>
  </a-row>
</template>

<script
  setup
  lang="ts"
  generic="ScreenSize extends string, FullScreen extends string, Monitor extends string"
>
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

defineProps<{ disabled: boolean }>()
const screenSize = defineModel<ScreenSize>('screenSize', { required: true })
const fullScreen = defineModel<FullScreen>('fullScreen', { required: true })
const popupWindow = defineModel<boolean>('popupWindow', { required: true })
const dx12 = defineModel<boolean>('dx12', { required: true })
const monitor = defineModel<Monitor>('monitor', { required: true })
const advancedArguments = defineModel<string>('advancedArguments', { required: true })

const emit = defineEmits<{
  'save-screen-size': [value: ScreenSize]
  'save-full-screen': [value: FullScreen]
  'save-popup-window': [value: boolean]
  'save-dx12': [value: boolean]
  'save-monitor': [value: Monitor]
  'save-advanced-arguments': [value: string]
}>()

const { t } = useI18n()

const screenSizeOptions = [
  { label: '1920x1080', value: '1920x1080' },
  { label: '2560x1440', value: '2560x1440' },
  { label: '3840x2160', value: '3840x2160' },
]
const fullScreenOptions = [
  { label: t('core.edit.zzzodFullScreenWindowed'), value: '0' },
  { label: t('core.edit.zzzodFullScreenFullscreen'), value: '1' },
]
const monitorOptions = [
  { label: '1', value: '1' },
  { label: '2', value: '2' },
  { label: '3', value: '3' },
  { label: '4', value: '4' },
]
</script>
