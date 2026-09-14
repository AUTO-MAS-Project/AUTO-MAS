<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { usePerformanceStore } from '@/stores/performance'

interface Shard {
  char: string
  glyph: string
  dx: number
  dy: number
  rotate: number
  scale: number
  delay: number
}

const GLYPHS =
  'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{};:,.<>/?'

// 前两个常量要与 .shatter-char 的 transition-duration 保持一致
const FLY_MS = 200
const SETTLE_MS = 460
const STAGGER_MS = 16
/** 飞散时留一点可见度，否则「打碎」只剩淡出，看不到碎片 */
const FLY_OPACITY = 0.32

const props = defineProps<{ text: string }>()

const performanceStore = usePerformanceStore()
const shards = ref<Shard[]>([])
const generation = ref(0)
const flying = ref(false)

let flyTimer: number | null = null
let settleFrame: number | null = null
let revealFrame: number | null = null

const randomGlyph = () => GLYPHS[Math.floor(Math.random() * GLYPHS.length)]

// 碎片朝句子两侧炸开：离中心越远，横向初速度越大
const buildShards = (text: string): Shard[] => {
  const characters = Array.from(text)
  const center = (characters.length - 1) / 2

  return characters.map((char, index) => ({
    char,
    glyph: char === ' ' ? ' ' : randomGlyph(),
    dx: Math.round((index - center) * 8 + (Math.random() - 0.5) * 150),
    dy: Math.round((Math.random() - 0.5) * 120),
    rotate: Math.round((Math.random() - 0.5) * 200),
    scale: 0.3 + Math.random() * 0.9,
    delay: index * STAGGER_MS,
  }))
}

const stopTimers = () => {
  if (flyTimer !== null) {
    window.clearTimeout(flyTimer)
    flyTimer = null
  }
  if (settleFrame !== null) {
    cancelAnimationFrame(settleFrame)
    settleFrame = null
  }
  if (revealFrame !== null) {
    cancelAnimationFrame(revealFrame)
    revealFrame = null
  }
}

// 碎片快要落位时才把乱码换成真字，看上去才是「拼合」而不是整体替换
const revealSettled = () => {
  const startedAt = performance.now()

  const tick = (now: number) => {
    const elapsed = now - startedAt
    let pending = false

    for (const shard of shards.value) {
      if (shard.glyph === shard.char) continue
      if (elapsed >= shard.delay + SETTLE_MS - 80) {
        shard.glyph = shard.char
      } else {
        pending = true
      }
    }

    revealFrame = pending ? requestAnimationFrame(tick) : null
  }

  revealFrame = requestAnimationFrame(tick)
}

const settleNewShards = (text: string) => {
  shards.value = buildShards(text)
  generation.value += 1

  // 先让新碎片以四散状态渲染一帧，再撤掉飞散态触发聚合过渡
  void nextTick().then(() => {
    settleFrame = requestAnimationFrame(() => {
      settleFrame = requestAnimationFrame(() => {
        settleFrame = null
        flying.value = false
        revealSettled()
      })
    })
  })
}

const play = (text: string) => {
  stopTimers()

  if (performanceStore.isLowPower) {
    const staticShards = buildShards(text)
    for (const shard of staticShards) shard.glyph = shard.char
    shards.value = staticShards
    generation.value += 1
    flying.value = false
    return
  }

  flying.value = true

  // 首次渲染没有旧句子可炸，直接聚合；之后都先炸开旧句子再换新碎片
  if (!shards.value.length) {
    settleNewShards(text)
    return
  }

  flyTimer = window.setTimeout(() => {
    flyTimer = null
    settleNewShards(text)
  }, FLY_MS)
}

const charStyle = (shard: Shard) => ({
  transform: flying.value
    ? `translate3d(${shard.dx}px, ${shard.dy}px, 0) rotate(${shard.rotate}deg) scale(${shard.scale})`
    : 'translate3d(0, 0, 0) rotate(0deg) scale(1)',
  opacity: flying.value ? FLY_OPACITY : 1,
  filter: flying.value ? 'blur(3px)' : 'blur(0)',
  transitionDelay: `${flying.value ? 0 : shard.delay}ms`,
})

watch(() => props.text, play, { immediate: true })

onUnmounted(stopTimers)
</script>

<template>
  <span class="shatter-text" :aria-label="props.text" role="text">
    <span
      v-for="(shard, index) in shards"
      :key="`${generation}-${index}`"
      class="shatter-char"
      :class="{
        'shatter-char--flying': flying,
        'shatter-char--scrambled': shard.glyph !== shard.char,
      }"
      :style="charStyle(shard)"
      aria-hidden="true"
    >{{ shard.glyph }}</span>
  </span>
</template>

<style scoped>
.shatter-text {
  display: inline-block;
  white-space: pre-wrap;
}

.shatter-char {
  display: inline-block;
  transform-origin: 50% 60%;
  will-change: transform, opacity, filter;
  transition-property: transform, opacity, filter;
  transition-duration: 460ms, 320ms, 320ms;
  /* 落位时带一点回弹，像碎片「啪」地吸附回原位 */
  transition-timing-function: cubic-bezier(0.2, 1.35, 0.4, 1), ease-out, ease-out;
}

.shatter-char--flying {
  transition-duration: 200ms, 200ms, 200ms;
  transition-timing-function: ease-in, ease-in, ease-in;
}

.shatter-char--scrambled {
  color: var(--ant-color-text-secondary);
}
</style>
