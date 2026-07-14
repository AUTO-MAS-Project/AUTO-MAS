<template>
  <div class="plugin-schema-element">
    <a-spin v-if="loading" tip="正在加载插件组件" />
    <a-alert
      v-else-if="errorMessage"
      type="warning"
      show-icon
      message="插件组件加载失败"
      :description="errorMessage"
    >
      <template #action>
        <a-button size="small" @click="loadElement">重试</a-button>
      </template>
    </a-alert>
    <component
      :is="descriptor.element_tag"
      v-else
      ref="elementRef"
      class="plugin-schema-element__root"
    />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { ensurePluginFrontendElement } from '@/plugin/pluginFrontendLoader'
import type {
  PluginFrontendElementDescriptor,
  PluginSchemaFieldChangeDetail,
  PluginSchemaFormPatchDetail,
} from '@/types/pluginFrontend'

const props = defineProps<{
  descriptor: PluginFrontendElementDescriptor
  scriptId: string
  userId?: string
  scriptConfig: Record<string, unknown>
  modelValue: Record<string, unknown>
  fieldPath?: string
  mode: 'create' | 'edit'
  extensionProps?: Record<string, unknown>
}>()

const emit = defineEmits<{
  (event: 'field-change', detail: PluginSchemaFieldChangeDetail): void
  (event: 'form-patch', detail: PluginSchemaFormPatchDetail): void
}>()

const elementRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const errorMessage = ref('')
let syncingProperties = false

const handleFieldChange = (event: Event) => {
  if (syncingProperties) return
  const detail = (event as CustomEvent<PluginSchemaFieldChangeDetail>).detail
  if (detail && typeof detail.path === 'string') {
    emit('field-change', detail)
  }
}

const handleFormPatch = (event: Event) => {
  if (syncingProperties) return
  const detail = (event as CustomEvent<PluginSchemaFormPatchDetail>).detail
  if (detail?.patch && typeof detail.patch === 'object') {
    emit('form-patch', detail)
  }
}

const detachListeners = () => {
  elementRef.value?.removeEventListener('field-change', handleFieldChange)
  elementRef.value?.removeEventListener('form-patch', handleFormPatch)
}

const syncProperties = async () => {
  await nextTick()
  const element = elementRef.value
  if (!element) return
  syncingProperties = true
  Object.assign(element, {
    scriptId: props.scriptId,
    userId: props.userId,
    scriptConfig: props.scriptConfig,
    modelValue: props.modelValue,
    fieldPath: props.fieldPath,
    mode: props.mode,
    extensionProps: props.extensionProps || {},
  })
  queueMicrotask(() => {
    syncingProperties = false
  })
}

const attachListeners = async () => {
  await nextTick()
  const element = elementRef.value
  if (!element) return
  detachListeners()
  element.addEventListener('field-change', handleFieldChange)
  element.addEventListener('form-patch', handleFormPatch)
  await syncProperties()
}

const loadElement = async () => {
  loading.value = true
  errorMessage.value = ''
  detachListeners()
  try {
    await ensurePluginFrontendElement(props.descriptor)
    loading.value = false
    await attachListeners()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
    loading.value = false
  }
}

watch(() => props.descriptor, loadElement, { deep: true, immediate: true })
watch(
  () => [
    props.scriptId,
    props.userId,
    props.scriptConfig,
    props.modelValue,
    props.fieldPath,
    props.mode,
    props.extensionProps,
  ],
  syncProperties,
  { deep: true }
)

onBeforeUnmount(detachListeners)
</script>

<style scoped>
.plugin-schema-element,
.plugin-schema-element__root {
  display: block;
  width: 100%;
}
</style>
