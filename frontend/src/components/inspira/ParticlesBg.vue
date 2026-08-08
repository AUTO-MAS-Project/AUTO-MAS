<template>
  <canvas ref="canvasRef" class="particles-bg" aria-hidden="true" />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

interface ParticleColor {
  red: number
  green: number
  blue: number
}

interface Particle {
  x: number
  y: number
  translateX: number
  translateY: number
  size: number
  alpha: number
  targetAlpha: number
  dx: number
  dy: number
  magnetism: number
}

interface Pointer {
  x: number
  y: number
  active: boolean
  radius: number
}

const props = withDefaults(
  defineProps<{
    color?: string
    quantity?: number
    staticity?: number
    ease?: number
  }>(),
  {
    color: '#FFF',
    quantity: 100,
    staticity: 50,
    ease: 50,
  }
)

const canvasRef = ref<HTMLCanvasElement | null>(null)

let canvasContext: CanvasRenderingContext2D | null = null
let containerElement: HTMLElement | null = null
let resizeObserver: ResizeObserver | null = null
let reducedMotionQuery: MediaQueryList | null = null
let animationFrameId: number | null = null
let isMounted = false
let width = 0
let height = 0
let particles: Particle[] = []
let particleColor = parseHexColor(props.color)

const pointer: Pointer = {
  x: 0,
  y: 0,
  active: false,
  radius: 120,
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function lerp(start: number, end: number, amount: number) {
  return start + (end - start) * amount
}

function parseHexColor(color: string): ParticleColor {
  const normalized = color.trim().replace(/^#/, '')
  const expanded =
    normalized.length === 3
      ? normalized
          .split('')
          .map(value => `${value}${value}`)
          .join('')
      : normalized

  if (!/^[0-9a-f]{6}$/i.test(expanded)) {
    return { red: 255, green: 255, blue: 255 }
  }

  return {
    red: Number.parseInt(expanded.slice(0, 2), 16),
    green: Number.parseInt(expanded.slice(2, 4), 16),
    blue: Number.parseInt(expanded.slice(4, 6), 16),
  }
}

function createParticles() {
  const count = Math.max(0, Math.floor(props.quantity))

  particles = Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    translateX: 0,
    translateY: 0,
    size: Math.random() * 1.3 + 0.7,
    alpha: 0,
    targetAlpha: Math.random() * 0.35 + 0.1,
    dx: (Math.random() - 0.5) * 0.12,
    dy: (Math.random() - 0.5) * 0.12,
    magnetism: Math.random() * 1.2 + 0.4,
  }))
}

function drawParticles() {
  if (!canvasContext || width <= 0 || height <= 0) {
    return
  }

  canvasContext.clearRect(0, 0, width, height)

  for (const particle of particles) {
    canvasContext.beginPath()
    canvasContext.arc(
      particle.x + particle.translateX,
      particle.y + particle.translateY,
      particle.size,
      0,
      Math.PI * 2
    )
    canvasContext.fillStyle = `rgba(${particleColor.red}, ${particleColor.green}, ${particleColor.blue}, ${particle.alpha})`
    canvasContext.fill()
  }
}

function updateParticles() {
  const movementEase = clamp(props.ease / 100, 0.02, 0.5)
  const staticity = Math.max(1, props.staticity)

  for (const particle of particles) {
    const currentX = particle.x + particle.translateX
    const currentY = particle.y + particle.translateY

    if (pointer.active) {
      const distanceX = pointer.x - currentX
      const distanceY = pointer.y - currentY
      const distance = Math.hypot(distanceX, distanceY)

      if (distance < pointer.radius) {
        const force = (pointer.radius - distance) / pointer.radius
        const angle = Math.atan2(distanceY, distanceX)
        const movement = (force * particle.magnetism * 50) / staticity

        particle.translateX -= Math.cos(angle) * movement
        particle.translateY -= Math.sin(angle) * movement
      }
    }

    particle.translateX = lerp(particle.translateX, 0, movementEase)
    particle.translateY = lerp(particle.translateY, 0, movementEase)
    particle.x += particle.dx
    particle.y += particle.dy
    particle.alpha = lerp(particle.alpha, particle.targetAlpha, 0.04)

    if (particle.x < -particle.size) {
      particle.x = width + particle.size
    } else if (particle.x > width + particle.size) {
      particle.x = -particle.size
    }

    if (particle.y < -particle.size) {
      particle.y = height + particle.size
    } else if (particle.y > height + particle.size) {
      particle.y = -particle.size
    }
  }
}

function animate() {
  updateParticles()
  drawParticles()
  animationFrameId = window.requestAnimationFrame(animate)
}

function stopAnimation() {
  if (animationFrameId === null) {
    return
  }

  window.cancelAnimationFrame(animationFrameId)
  animationFrameId = null
}

function startAnimation() {
  stopAnimation()

  if (reducedMotionQuery?.matches || typeof window.requestAnimationFrame !== 'function') {
    drawParticles()
    return
  }

  animationFrameId = window.requestAnimationFrame(animate)
}

function resizeCanvas() {
  if (!canvasRef.value || !containerElement || !canvasContext) {
    return
  }

  const rect = containerElement.getBoundingClientRect()
  width = Math.max(1, Math.floor(rect.width || containerElement.clientWidth))
  height = Math.max(1, Math.floor(rect.height || containerElement.clientHeight))

  const devicePixelRatio = Math.min(window.devicePixelRatio || 1, 2)
  canvasRef.value.width = Math.floor(width * devicePixelRatio)
  canvasRef.value.height = Math.floor(height * devicePixelRatio)
  canvasContext.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)

  createParticles()
  drawParticles()
}

function handlePointerMove(event: PointerEvent) {
  if (!containerElement) {
    return
  }

  const rect = containerElement.getBoundingClientRect()
  pointer.x = event.clientX - rect.left
  pointer.y = event.clientY - rect.top
  pointer.active = true
}

function handlePointerLeave() {
  pointer.active = false
}

function handleReducedMotionChange(event: MediaQueryListEvent) {
  if (event.matches) {
    stopAnimation()
    drawParticles()
    return
  }

  startAnimation()
}

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) {
    return
  }

  containerElement = canvas.parentElement
  canvasContext = canvas.getContext('2d')
  if (!containerElement || !canvasContext) {
    return
  }

  isMounted = true
  containerElement.addEventListener('pointermove', handlePointerMove)
  containerElement.addEventListener('pointerleave', handlePointerLeave)

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(resizeCanvas)
    resizeObserver.observe(containerElement)
  }

  if (typeof window.matchMedia === 'function') {
    reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    reducedMotionQuery.addEventListener('change', handleReducedMotionChange)
  }

  resizeCanvas()
  startAnimation()
})

onUnmounted(() => {
  isMounted = false
  stopAnimation()
  resizeObserver?.disconnect()
  reducedMotionQuery?.removeEventListener('change', handleReducedMotionChange)
  containerElement?.removeEventListener('pointermove', handlePointerMove)
  containerElement?.removeEventListener('pointerleave', handlePointerLeave)
  canvasContext = null
  containerElement = null
  particles = []
})

watch(
  () => [props.color, props.quantity],
  () => {
    particleColor = parseHexColor(props.color)
    if (isMounted) {
      resizeCanvas()
    }
  }
)
</script>

<style scoped>
.particles-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  pointer-events: none;
}
</style>
