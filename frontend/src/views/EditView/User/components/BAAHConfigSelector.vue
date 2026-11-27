<template>
  <a-form-item name="configName">
    <template #label>
      <FieldLabelWithHint
        :text="t('core.edit.baahConfigName')"
        :hint="t('core.edit.baahConfigNameHint')"
        variant="form"
      />
    </template>
    <div class="config-controls">
      <a-select
        :value="modelValue"
        :placeholder="t('core.edit.baahConfigNamePlaceholder')"
        :disabled="disabled || generating || saving"
        :loading="namesLoading"
        :options="options"
        class="config-select"
        size="large"
        show-search
        option-filter-prop="label"
        @dropdown-visible-change="(open: boolean) => open && loadNames()"
        @change="(value: unknown) => selectConfig(String(value))"
      />
      <a-button size="large" :disabled="disabled || saving" :loading="generating" @click="generate">
        {{ t('core.edit.baahGenerateRecommended') }}
      </a-button>
    </div>
    <a-typography-paragraph type="secondary" class="config-hint">
      {{ t('core.edit.baahRecommendedHint') }}
    </a-typography-paragraph>
  </a-form-item>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { BaahService, type ComboBoxItem } from '@/api'
import { BAAHSetupService } from '@/composables/useAdapterSetupApi'
import { getApiErrorMessage } from '@/utils/apiError'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

const props = defineProps<{
  modelValue: string
  scriptId: string
  disabled: boolean
  saveSelection: (name: string) => Promise<boolean>
}>()
const emit = defineEmits<{ 'update:modelValue': [name: string] }>()
const { t } = useI18n()
const options = ref<{ label: string; value: string }[]>([])
const namesLoading = ref(false)
const generating = ref(false)
const saving = ref(false)
let namesRequest = 0
let active = true

async function loadNames() {
  const request = ++namesRequest
  const scriptId = props.scriptId
  namesLoading.value = true
  try {
    const response = await BaahService.getBaahConfigNamesApiApiScriptsBaahConfigNamesGet(scriptId)
    if (!active || request !== namesRequest || scriptId !== props.scriptId) return
    if (response.code !== 200) throw new Error(response.message)
    options.value = (response.data ?? [])
      .filter((item): item is ComboBoxItem & { value: string } => item.value != null)
      .map(item => ({ label: item.label, value: item.value }))
  } catch (error) {
    if (active && request === namesRequest && scriptId === props.scriptId) {
      message.error(getApiErrorMessage(error, t('core.edit.baahConfigNamesFailed')))
    }
  } finally {
    if (active && request === namesRequest) namesLoading.value = false
  }
}

async function selectConfig(name: string) {
  saving.value = true
  try {
    const saved = await props.saveSelection(name)
    if (saved && active) emit('update:modelValue', name)
    return saved
  } finally {
    saving.value = false
  }
}

async function generate() {
  if (generating.value || saving.value || props.disabled) return
  generating.value = true
  const scriptId = props.scriptId
  try {
    const response =
      await BAAHSetupService.createBaahRecommendedConfigApiApiScriptsBaahConfigCreateRecommendedPost(
        {
          scriptId,
        }
      )
    if (response.code !== 200 || !response.configName) {
      throw new Error(response.message || t('core.edit.baahRecommendedFailed'))
    }
    if (!active || scriptId !== props.scriptId) return
    // 让生成前发出的列表请求失效，避免旧列表覆盖刚创建的文件名。
    namesRequest++
    namesLoading.value = false
    const name = response.configName
    options.value = [...options.value, { label: name, value: name }]
    if (await selectConfig(name)) {
      message.success(t('core.edit.baahRecommendedCreated', { name }))
    } else {
      message.warning(t('core.edit.baahRecommendedNotSelected', { name }))
    }
  } catch (error) {
    if (active && scriptId === props.scriptId) {
      message.error(getApiErrorMessage(error, t('core.edit.baahRecommendedFailed')))
    }
  } finally {
    generating.value = false
  }
}

watch(
  () => props.scriptId,
  () => {
    void loadNames()
  },
  { immediate: true }
)
onUnmounted(() => {
  active = false
  namesRequest++
})
</script>

<style scoped>
.config-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.config-select {
  width: 320px;
  max-width: 100%;
}

.config-hint {
  margin: 8px 0 0;
}
</style>
