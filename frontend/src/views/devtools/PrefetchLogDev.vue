<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import SchedulerLogPanel from '../scheduler/SchedulerLogPanel.vue'
import type { WSTaskPrefetchData } from '@/services/websocket/types'

const method = ref('FluxDown')
const elapsed = ref(0)
const running = ref(false)
const log = ref('')
const prefetch = ref<WSTaskPrefetchData | null>(null)
let timer: ReturnType<typeof setInterval> | undefined
const percent = computed(() => Math.min(100, Math.max(0, elapsed.value - 3) * 2))

const stop = () => {
  clearInterval(timer)
  timer = undefined
  running.value = false
}
const tick = () => {
  elapsed.value++
  if (elapsed.value % 3 === 0) {
    log.value += `[模拟 MAA] 理智作战运行中，已完成 ${Math.floor(elapsed.value / 3)} 次作战\n`
  }
  if (elapsed.value < 3) {
    prefetch.value = { target: 'MaaEnd', status: '正在检查更新' }
  } else if (percent.value < 100) {
    prefetch.value = {
      target: 'MaaEnd',
      status: '下载中',
      package: 'MaaEnd-update-win-x86_64.zip',
      method: method.value,
      progress: `${percent.value.toFixed(1)}%`,
      size: `${(percent.value * 2).toFixed(1)}/200.0 MiB`,
      rate: '4.0 MiB/s',
    }
  } else {
    prefetch.value = { target: 'MaaEnd', status: '检查／准备完成' }
    if (elapsed.value > 60) stop()
  }
}
const start = () => {
  stop()
  elapsed.value = 0
  log.value =
    '[模拟] 此场景不会运行真实脚本或下载文件\n[模拟 MAA] 开始运行，等待首节点完成\n[模拟 MAA] 首节点完成，检查下一项 MaaEnd 更新\n'
  running.value = true
  tick()
  timer = setInterval(tick, 1000)
}
onMounted(start)
onUnmounted(stop)
</script>

<template>
  <div class="prefetch-dev-page">
    <a-typography-title :level="3">预下载日志模拟</a-typography-title>
    <a-alert
      message="模拟数据：MAA 持续运行，同时检查并预下载 MaaEnd 更新。不会运行真实脚本或写入下载文件。"
      type="info"
      show-icon
    />
    <a-flex wrap="wrap" align="center" gap="12" class="simulation-controls">
      <a-tag color="processing">MAA · 运行中</a-tag>
      <a-tag :color="percent >= 100 ? 'success' : 'default'"
        >MaaEnd · {{ percent >= 100 ? '预下载完成' : '等待运行' }}</a-tag
      >
      <a-select v-model:value="method" aria-label="模拟下载方式" class="method-select">
        <a-select-option value="httpx">httpx</a-select-option>
        <a-select-option value="FluxDown">FluxDown</a-select-option>
      </a-select>
      <a-button type="primary" @click="start">重新模拟</a-button>
      <a-button :disabled="!running" @click="stop">暂停模拟</a-button>
    </a-flex>
    <div class="demo-log-panel">
      <SchedulerLogPanel :log-content="log" :prefetch="prefetch" :first-line="1" :active="true" />
    </div>
  </div>
</template>

<style scoped>
.prefetch-dev-page {
  padding: 24px;
}
.simulation-controls {
  margin: 16px 0;
}
.method-select {
  width: 140px;
}
.demo-log-panel {
  height: 420px;
}
.demo-log-panel :deep(.log-panel) {
  height: 100%;
}
</style>
