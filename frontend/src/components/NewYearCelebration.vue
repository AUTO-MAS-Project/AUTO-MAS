<script setup lang="ts">
import { ref, useTemplateRef, watch } from 'vue'
import { usePreferredReducedMotion } from '@vueuse/core'
import { usePerformanceStore } from '@/stores/performance'

const STORAGE_KEY = 'auto-mas:new-year:last-played-year'
const FIRST_CELEBRATION_YEAR = 2027
const DURATION_MS = 4200
const COLORS = ['#ff5978', '#ffcf56', '#54d6bb', '#6c9dff', '#b78bfa', '#ff914d']

const logger = window.electronAPI.getLogger('新年彩蛋')
const performanceStore = usePerformanceStore()
const reducedMotion = usePreferredReducedMotion()
const canvas = useTemplateRef<HTMLCanvasElement>('canvas')
const finished = ref(false)
let started = false

watch(
  [canvas, () => performanceStore.isLowPower, reducedMotion],
  ([element, lowPower, motion], _, onCleanup) => {
    if (!element || lowPower || motion === 'reduce' || started) return

    const currentYear = new Date().getFullYear()
    if (currentYear < FIRST_CELEBRATION_YEAR) {
      finished.value = true
      return
    }

    // 仅在可见主界面准备好播放时领取，静默启动不提前消耗这次彩蛋。
    try {
      if (localStorage.getItem(STORAGE_KEY) === String(currentYear)) {
        finished.value = true
        return
      }
    } catch (error) {
      logger.warn('无法读取新年彩蛋记录，跳过播放', error)
      finished.value = true
      return
    }

    const context = element.getContext('2d')
    if (!context) {
      finished.value = true
      return
    }

    let width = 0
    let height = 0
    let frame = 0
    const resize = () => {
      const bounds = element.getBoundingClientRect()
      width = bounds.width
      height = bounds.height
      const scale = Math.min(window.devicePixelRatio, 2)
      element.width = Math.round(width * scale)
      element.height = Math.round(height * scale)
      context.setTransform(scale, 0, 0, scale, 0, 0)
    }
    resize()

    // 三轮双侧礼炮；按实际经过的时间绘制，帧率不会改变飘落速度。
    const particles = Array.from({ length: 240 }, (_, index) => ({
      fromLeft: index % 2 === 0,
      delay: Math.floor(index / 80) * 0.18,
      speedX: 0.3 + Math.random() * 0.25,
      speedY: 0.95 + Math.random() * 0.4,
      size: 5 + Math.random() * 5,
      angle: Math.random() * Math.PI,
      spin: (Math.random() - 0.5) * 12,
      color: COLORS[index % COLORS.length],
      round: index % 6 === 0,
    }))

    const draw = (now: number) => {
      const elapsed = now - beganAt
      context.clearRect(0, 0, width, height)
      if (elapsed >= DURATION_MS) {
        finished.value = true
        return
      }

      context.globalAlpha = Math.min(1, (DURATION_MS - elapsed) / 800)
      for (const particle of particles) {
        const age = elapsed / 1000 - particle.delay
        if (age < 0) continue
        const direction = particle.fromLeft ? 1 : -1
        const originX = particle.fromLeft ? -10 : width + 10
        const x =
          originX +
          direction * Math.max(height, width * 0.55) * particle.speedX * age +
          Math.sin(age * 3 + particle.angle) * 12
        const y = height + 10 - height * particle.speedY * age + height * 0.4 * age * age
        context.save()
        context.translate(x, y)
        context.rotate(particle.angle + particle.spin * age)
        context.fillStyle = particle.color
        if (particle.round) {
          context.beginPath()
          context.arc(0, 0, particle.size / 2, 0, Math.PI * 2)
          context.fill()
        } else {
          const flutter = 0.3 + Math.abs(Math.cos(age * 7 + particle.angle)) * 0.7
          context.fillRect(
            -particle.size / 2,
            -particle.size / 4,
            particle.size,
            particle.size * 0.5 * flutter
          )
        }
        context.restore()
      }
      frame = requestAnimationFrame(draw)
    }

    try {
      localStorage.setItem(STORAGE_KEY, String(currentYear))
    } catch (error) {
      // 无法持久保存时不播放，避免每次启动都重复庆祝。
      logger.warn('无法保存新年彩蛋记录，跳过播放', error)
      finished.value = true
      return
    }

    started = true
    const beganAt = performance.now()
    window.addEventListener('resize', resize)
    frame = requestAnimationFrame(draw)
    onCleanup(() => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
      // 切到后台或启用低性能 / 减少动态效果时，立即结束本次播放。
      finished.value = true
    })
  },
  { flush: 'post' }
)
</script>

<template>
  <canvas v-if="!finished" ref="canvas" class="new-year-confetti" aria-hidden="true" />
</template>

<style scoped>
.new-year-confetti {
  position: fixed;
  inset: 32px 0 0;
  width: 100%;
  height: calc(100% - 32px);
  z-index: 1001;
  pointer-events: none;
}
</style>
