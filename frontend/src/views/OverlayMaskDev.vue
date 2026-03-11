<template>
  <div class="mask-dev-page">
    <div class="page-header">
      <h1>全屏遮罩彩蛋测试</h1>
      <p class="description">用于单独调试 OverlayRainMask 组件，不受调度中心触发时间限制。</p>
    </div>

    <a-card title="手动触发" class="control-card">
      <a-space size="middle" wrap>
        <a-button type="primary" size="large" @click="triggerMask">触发彩蛋</a-button>
        <a-button size="large" @click="maskVisible = false">关闭遮罩</a-button>
        <a-button size="large" @click="setAprilFoolsFlag">手动设置为已触发</a-button>
        <a-button danger size="large" @click="clearAprilFoolsFlag">清除4.1触发标志位</a-button>
      </a-space>

      <div class="hint">
        <p>提示：遮罩显示后，单击任意位置可退出。</p>
        <p>触顶停机次数：{{ stoppedCount }}</p>
      </div>
    </a-card>

    <a-card title="4.1 触发状态调试" class="debug-card">
      <a-descriptions bordered :column="1" size="small">
        <a-descriptions-item label="当前本地时间">
          {{ debugInfo.localNow }}
        </a-descriptions-item>
        <a-descriptions-item label="当前 UTC 时间">
          {{ debugInfo.utcNow }}
        </a-descriptions-item>
        <a-descriptions-item label="当前 UTC+8 时间">
          {{ debugInfo.utc8Now }}
        </a-descriptions-item>
        <a-descriptions-item label="UTC+8 是否为 4 月 1 日">
          <a-tag :color="debugInfo.isUtc8AprilFools ? 'success' : 'default'">
            {{ debugInfo.isUtc8AprilFools ? '是' : '否' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="当前是否在触发窗口内">
          <a-tag :color="debugInfo.isInWindow ? 'success' : 'warning'">
            {{ debugInfo.isInWindow ? '在窗口内' : '不在窗口内' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="当前窗口（本地时间）">
          {{ debugInfo.windowLocalStart }} ~ {{ debugInfo.windowLocalEnd }}
        </a-descriptions-item>
        <a-descriptions-item label="当前窗口（UTC+8）">
          {{ debugInfo.windowUtc8Start }} ~ {{ debugInfo.windowUtc8End }}
        </a-descriptions-item>
        <a-descriptions-item label="标志位 Key">
          <span class="mono">{{ debugInfo.storageKey }}</span>
        </a-descriptions-item>
        <a-descriptions-item label="标志位 Value">
          <a-tag :color="debugInfo.storageValue === '1' ? 'error' : 'success'">
            {{ debugInfo.storageValue ?? '(未设置)' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="可触发结论">
          <a-tag :color="debugInfo.canTriggerByRule ? 'success' : 'error'">
            {{ debugInfo.canTriggerByRule ? '当前点击开始执行可触发' : '当前点击开始执行不可触发' }}
          </a-tag>
        </a-descriptions-item>
      </a-descriptions>
    </a-card>

    <OverlayRainMask
      v-model="maskVisible"
      :opacity="0.75"
      :block-size="128"
      @stopped="handleStopped"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import OverlayRainMask from '@/components/OverlayRainMask.vue'

const maskVisible = ref(false)
const stoppedCount = ref(0)
const nowMs = ref(Date.now())
const APRIL_FOOLS_STORAGE_PREFIX = 'scheduler-april-fools-triggered-'
let nowTimer: ReturnType<typeof setInterval> | null = null

const EIGHT_HOURS_MS = 8 * 60 * 60 * 1000

const formatDateTimeLocal = (date: Date) => {
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

const formatDateTimeUtc = (ms: number) => {
  const d = new Date(ms)
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${y}-${m}-${day} ${hh}:${mm}:${ss}`
}

const formatDateTimeUtc8 = (ms: number) => {
  return formatDateTimeUtc(ms + EIGHT_HOURS_MS)
}

const getUtc8DateParts = (ms: number) => {
  const utc8 = new Date(ms + EIGHT_HOURS_MS)
  return {
    year: utc8.getUTCFullYear(),
    month: utc8.getUTCMonth() + 1,
    day: utc8.getUTCDate(),
  }
}

const getUtc8Year = () => {
  return getUtc8DateParts(nowMs.value).year
}

const triggerMask = () => {
  maskVisible.value = true
}

const setAprilFoolsFlag = () => {
  const key = `${APRIL_FOOLS_STORAGE_PREFIX}${getUtc8Year()}`
  window.localStorage.setItem(key, '1')
  message.success(`已设置标志位：${key} = 1`)
}

const clearAprilFoolsFlag = () => {
  const key = `${APRIL_FOOLS_STORAGE_PREFIX}${getUtc8Year()}`
  window.localStorage.removeItem(key)
  message.success(`已清除标志位：${key}`)
}

const handleStopped = () => {
  stoppedCount.value += 1
  message.success('已触顶停机，动画循环已停止')
}

const debugInfo = computed(() => {
  const ms = nowMs.value
  const localNow = formatDateTimeLocal(new Date(ms))
  const utcNow = formatDateTimeUtc(ms)
  const utc8Now = formatDateTimeUtc8(ms)

  const utc8Parts = getUtc8DateParts(ms)
  const isUtc8AprilFools = utc8Parts.month === 4 && utc8Parts.day === 1

  // UTC+8 的 4 月 1 日 00:00:00 - 23:59:59.999
  const startMs = Date.UTC(utc8Parts.year, 3, 1, 0, 0, 0, 0) - EIGHT_HOURS_MS
  const endMs = startMs + 24 * 60 * 60 * 1000 - 1
  const isInWindow = ms >= startMs && ms <= endMs

  const storageKey = `${APRIL_FOOLS_STORAGE_PREFIX}${utc8Parts.year}`
  const storageValue = window.localStorage.getItem(storageKey)
  const canTriggerByRule = isInWindow && storageValue !== '1'

  return {
    localNow,
    utcNow,
    utc8Now,
    isUtc8AprilFools,
    isInWindow,
    windowLocalStart: formatDateTimeLocal(new Date(startMs)),
    windowLocalEnd: formatDateTimeLocal(new Date(endMs)),
    windowUtc8Start: formatDateTimeUtc8(startMs),
    windowUtc8End: formatDateTimeUtc8(endMs),
    storageKey,
    storageValue,
    canTriggerByRule,
  }
})

onMounted(() => {
  nowTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (nowTimer) {
    clearInterval(nowTimer)
    nowTimer = null
  }
})
</script>

<style scoped>
.mask-dev-page {
  padding: 24px;
  max-width: 1000px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.description {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

.hint {
  margin-top: 16px;
  color: var(--ant-color-text-secondary);
}

.hint p {
  margin: 0 0 6px 0;
}

.debug-card {
  margin-top: 16px;
}

.mono {
  font-family: Consolas, Monaco, monospace;
}
</style>
