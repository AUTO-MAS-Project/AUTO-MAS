<script setup lang="ts">
import { onScopeDispose, ref, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ScriptMirrorCdkData } from '@/api'
import type { MAAScriptConfig } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import MirrorCdkStatusHint from '@/components/MirrorCdkStatusHint.vue'

const props = defineProps<{
  update: MAAScriptConfig['Update']
  ready: boolean
}>()
const emit = defineEmits<{
  change: [key: string, value: boolean | string]
  'update:cdk': [value: string]
  'update:enabled': [value: boolean]
}>()
const { queryMirrorCdk } = useScriptApi()
const checking = ref(false)
const state = ref<ScriptMirrorCdkData | null>(null)
let querySequence = 0

const invalidate = () => {
  querySequence += 1
  checking.value = false
  state.value = null
}
const refresh = async () => {
  if (!props.ready || !props.update.TakeoverEnabled || checking.value) return
  const sequence = ++querySequence
  checking.value = true
  try {
    const result = await queryMirrorCdk(props.update.MirrorChyanCDK ?? '')
    if (sequence === querySequence) state.value = result
  } finally {
    if (sequence === querySequence) checking.value = false
  }
}

// 输入时清除旧结论；打开页面、切换接管开关和失焦时才查询。
watch(() => props.update.MirrorChyanCDK, invalidate)
watch(
  () => [props.ready, props.update.TakeoverEnabled],
  () => {
    invalidate()
    void refresh()
  },
  { immediate: true }
)
onScopeDispose(invalidate)

const handleBlur = () => {
  emit('change', 'MirrorChyanCDK', props.update.MirrorChyanCDK ?? '')
  void refresh()
}
const handleEnabled = (enabled: boolean) => {
  emit('update:enabled', enabled)
  emit('change', 'TakeoverEnabled', enabled)
}
</script>

<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ $t('edit.updateTakeover') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="$t('edit.updateTakeoverTip')">
              <span class="form-label">
                {{ $t('edit.updateTakeoverSwitch') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-switch
            :checked="update.TakeoverEnabled"
            size="large"
            :disabled="!ready"
            @change="handleEnabled"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
        <a-form-item>
          <template #label>
            <a-tooltip :title="$t('edit.updateTakeoverCdkTip')">
              <span class="form-label">
                {{ $t('edit.updateTakeoverCdk') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            :value="update.MirrorChyanCDK"
            :placeholder="$t('edit.updateTakeoverCdkPlaceholder')"
            size="large"
            class="modern-input"
            autocomplete="off"
            :disabled="!ready || !update.TakeoverEnabled"
            @update:value="emit('update:cdk', $event)"
            @blur="handleBlur"
          />
          <MirrorCdkStatusHint :state="state" :checking="checking" @retry="refresh" />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>
