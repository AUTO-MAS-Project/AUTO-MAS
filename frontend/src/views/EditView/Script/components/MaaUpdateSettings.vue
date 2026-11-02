<script setup lang="ts">
import ProgramUpdateSettings from './ProgramUpdateSettings.vue'
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
  <ProgramUpdateSettings
    :ready="ready"
    :enabled="update.TakeoverEnabled"
    :channel="update.Channel"
    :cdk="update.MirrorChyanCDK"
    :title="t('core.edit.updateTakeover')"
    :hint="t('core.edit.updateTakeoverTip')"
    :cdk-hint="t('core.edit.updateTakeoverCdkTip')"
    @enabled="handleEnabled"
    @channel="handleChannel"
    @cdk="update = { ...update, MirrorChyanCDK: $event }"
    @save-cdk="handleBlur"
  >
    <template #cdk-status>
      <MirrorCdkStatusHint :state="state" :checking="checking" @retry="refresh" />
    </template>
  </ProgramUpdateSettings>
</template>
