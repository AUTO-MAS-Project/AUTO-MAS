<script setup lang="ts">
import { onMounted, onScopeDispose, shallowRef, watch } from 'vue'
import { StateView } from '@/components/ui'
import { pluginPanelTheme } from '@/composables/pluginPanelTheme'
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
const frame = shallowRef<HTMLIFrameElement | null>(null)
const { iframeUrl, frameHeight, status, start, stop, fail } = usePluginUiBridge(
  () => frame.value,
  () => props.editor,
  () => pluginPanelTheme.value
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
      () => props.mount.pageId,
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
  cleanup = () => {
    generation++
    stopWatch()
    unsubscribe(subscription)
    offConnected()
    offDisconnected()
  }
})

onScopeDispose(() => cleanup?.())
</script>

<template>
  <template v-if="status !== 'error'">
    <StateView :loading="status === 'loading'" :empty="!iframeUrl" overlay-loading>
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
    <slot v-if="status === 'ready'" />
  </template>
  <slot v-else name="fallback" />
</template>

<style scoped>
iframe {
  display: block;
  width: 100%;
  border: 0;
}
</style>
