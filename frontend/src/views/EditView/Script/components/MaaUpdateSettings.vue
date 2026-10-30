<script setup lang="ts">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ScriptMirrorCdkData } from '@/api'
import type { MAAScriptConfig } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import MirrorCdkStatusHint from '@/components/MirrorCdkStatusHint.vue'

const props = defineProps<{
  ready: boolean
}>()
const update = defineModel<MAAScriptConfig['Update']>('update', { required: true })
const emit = defineEmits<{
  change: [key: string, value: boolean | string]
}>()
const { t } = useI18n()
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
  if (!props.ready || !update.value.TakeoverEnabled || checking.value) return
  const sequence = ++querySequence
  checking.value = true
  try {
    const result = await queryMirrorCdk(update.value.MirrorChyanCDK ?? '')
    if (sequence === querySequence) state.value = result
  } finally {
    if (sequence === querySequence) checking.value = false
  }
}

// 输入时清除旧结论；打开页面、切换接管开关和失焦时才查询。
watch(() => update.value.MirrorChyanCDK, invalidate)
watch(
  () => [props.ready, update.value.TakeoverEnabled],
  () => {
    invalidate()
    void refresh()
  },
  { immediate: true }
)
onScopeDispose(invalidate)

const handleBlur = () => {
  emit('change', 'MirrorChyanCDK', update.value.MirrorChyanCDK ?? '')
  void refresh()
}
const handleEnabled = (enabled: boolean) => {
  update.value = { ...update.value, TakeoverEnabled: enabled }
  emit('change', 'TakeoverEnabled', enabled)
}
const handleChannel = (channel: 'stable' | 'beta') => {
  update.value = { ...update.value, Channel: channel }
  emit('change', 'Channel', channel)
}
</script>

<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('core.edit.updateTakeover') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item :label="t('core.edit.updateChannel')">
          <a-select
            :value="update.Channel"
            :disabled="!ready"
            size="large"
            :options="[
              { label: t('core.setting.channel.stable'), value: 'stable' },
              { label: t('core.setting.channel.beta'), value: 'beta' },
            ]"
            @change="handleChannel"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.updateTakeoverSwitch')"
              :hint="t('core.edit.updateTakeoverTip')"
              variant="form"
            />
          </template>
          <a-switch
            :checked="update.TakeoverEnabled"
            size="large"
            :disabled="!ready"
            @change="handleEnabled"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.updateTakeoverCdk')"
              :hint="t('core.edit.updateTakeoverCdkTip')"
              variant="form"
            />
          </template>
          <a-input-password
            :value="update.MirrorChyanCDK"
            :placeholder="t('core.edit.updateTakeoverCdkPlaceholder')"
            size="large"
            class="modern-input"
            autocomplete="off"
            :disabled="!ready || !update.TakeoverEnabled"
            @update:value="update = { ...update, MirrorChyanCDK: $event }"
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
