<script setup lang="ts">
import { onMounted, onScopeDispose, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { StateView } from '@/components/ui'
import {
  usePluginUiBridge,
  type PluginUiEditor,
  type PluginUiTarget,
  type WheelMount,
} from '@/composables/usePluginUiBridge'
import { connectionState, onConnected, onDisconnected } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { WS_ID_PLUGIN, WS_PLUGIN_CAPABILITIES_UPDATED } from '@/services/websocket/types'

const props = defineProps<{
  mount: WheelMount
  target: PluginUiTarget
  editor: PluginUiEditor
  refresh: () => Promise<boolean>
}>()
const { t } = useI18n()
const frame = shallowRef<HTMLIFrameElement | null>(null)
const { iframeUrl, frameHeight, status, start, stop, fail } = usePluginUiBridge(
  () => frame.value,
  () => props.editor
)
let cleanup: (() => void) | undefined

onMounted(() => {
  const connection = connectionState()
  let refreshing = false
  let generation = 0
  const remount = () => {
    if (connection.value !== 'open') fail()
    else if (!refreshing) start(props.mount, props.target)
  }
  const refresh = async () => {
    const pending = ++generation
    refreshing = true
    stop()
    status.value = 'loading'
    const available = await props.refresh()
    if (generation !== pending) return
    refreshing = false
    if (available) remount()
    else fail()
  }
  const stopWatch = watch(
    [
      () => props.mount.pluginName,
      () => props.mount.revision,
      () => props.mount.entry,
      () => props.mount.activationId,
      () => props.target.kind,
      () => props.target.scriptId,
      () => props.target.userId,
      () => props.target.planId,
      () => props.target.configUid,
    ],
    remount,
    { immediate: true, flush: 'sync' }
  )
  const subscription = subscribe(
    { id: WS_ID_PLUGIN, type: WS_PLUGIN_CAPABILITIES_UPDATED },
    refresh
  )
  const offConnected = onConnected(refresh)
  const offDisconnected = onDisconnected(() => {
    generation++
    refreshing = false
    fail()
  })
  retry = refresh
  cleanup = () => {
    generation++
    stopWatch()
    unsubscribe(subscription)
    offConnected()
    offDisconnected()
  }
})

let retry: () => Promise<void>
onScopeDispose(() => cleanup?.())
</script>

<template>
  <StateView
    :loading="status === 'loading'"
    :error="status === 'error' ? t('core.plugins.settingsLoadFailed') : null"
    :empty="!iframeUrl"
    overlay-loading
    @retry="retry()"
  >
    <iframe
      ref="frame"
      :key="iframeUrl"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
      :title="mount.pluginName"
      :src="iframeUrl"
      :style="{ height: frameHeight + 'px' }"
      @error="fail"
    />
  </StateView>
</template>

<style scoped>
iframe {
  display: block;
  width: 100%;
  border: 0;
}
</style>
