<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="overlay-rain-mask"
      :style="maskBackgroundStyle"
      @click="handleMaskClick"
    >
      <canvas ref="canvasRef" class="overlay-rain-mask__canvas"></canvas>
      <div class="overlay-rain-mask__exit-hint">单击任意位置可退出</div>
      <div class="overlay-rain-mask__float-layer">
        <span
          v-for="item in floatingTexts"
          :key="item.id"
          class="overlay-rain-mask__float-text"
          :style="getFloatTextStyle(item)"
        >
          {{ item.text }}
        </span>
      </div>
      <div v-if="comboLabel" :key="comboSerial" class="overlay-rain-mask__combo">
        {{ comboLabel }}
      </div>
      <div v-if="freezeFlashVisible" class="overlay-rain-mask__freeze-flash"></div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Bodies, Body, Composite, Engine, Events, World, type Body as MatterBody } from 'matter-js'

interface Props {
  modelValue?: boolean
  visible?: boolean
  opacity?: number
  blockSize?: number
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: false,
  visible: undefined,
  opacity: 0.75,
  blockSize: 64,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:visible': [value: boolean]
  stopped: []
  onStopped: []
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const floatingTexts = ref<FloatingTextItem[]>([])
const comboLabel = ref('')
const comboSerial = ref(0)
const freezeFlashVisible = ref(false)

const isOpen = computed(() => props.visible ?? props.modelValue)
const safeOpacity = computed(() => Math.min(1, Math.max(0, props.opacity)))
const safeBlockSize = computed(() => Math.min(256, Math.max(24, Math.round(props.blockSize))))
const maskBackgroundStyle = computed(() => {
  const alpha = safeOpacity.value
  return {
    backgroundImage: `linear-gradient(rgba(0, 0, 0, ${alpha}), rgba(0, 0, 0, ${alpha})), url('/prts.png')`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
  }
})

let engine: Engine | null = null
let canvasCtx: CanvasRenderingContext2D | null = null
let logoImage: HTMLImageElement | null = null
let animationFrameId: number | null = null
let spawnTimerId: number | null = null
let resizeHandler: (() => void) | null = null
let windTimerId: number | null = null
let comboHideTimerId: number | null = null
let freezeFlashTimerId: number | null = null

let worldWidth = 0
let worldHeight = 0
let dpr = 1

let borderWalls: MatterBody[] = []
let blockBodies: MatterBody[] = []
let blockBodyIds = new Set<number>()
let enteredViewportBodies = new WeakSet<MatterBody>()
type VisualEffectKind = 'normal' | 'mirror' | 'scale_down' | 'scale_up' | 'mirror_reverse'
interface VisualVariant {
  effect: VisualEffectKind
  drawScale: number
  isGold: boolean
}
interface SparkParticle {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  size: number
  color: string
}
interface FloatingTextItem {
  id: string
  text: string
  x: number
  y: number
  rotate: number
  size: number
  delay: number
  duration: number
  opacity: number
}
let blockVisualEffects = new WeakMap<MatterBody, VisualVariant>()
let sparkParticles: SparkParticle[] = []
let collisionHistory: number[] = []
let lastRenderAt = 0
let shakeStartAt = 0
let shakeEndAt = 0
let shakeMagnitude = 0
let emergencyStopped = false
const GOLD_BLOCK_PROBABILITY = 0.01
const FLOATING_TEXT_POOL = [
  '愚人节快乐',
  '自动化也会做梦',
  '今天允许离谱',
  '别眨眼',
  '就离谱一下',
  '今天没有 BUG',
  '物理引擎已失控',
  '随机就是艺术',
]
const DEFAULT_VARIANT: VisualVariant = {
  effect: 'normal',
  drawScale: 1,
  isGold: false,
}

const afterUpdateHandler = () => {
  if (!engine || emergencyStopped) return

  stabilizeBodies()

  if (hasReachedTopBoundary()) {
    emergencyStop()
  }
}

const randomInRange = (min: number, max: number) => {
  return Math.random() * (max - min) + min
}

const pickRandomVisualEffect = (): VisualVariant => {
  const effects: VisualEffectKind[] = [
    'normal',
    'mirror',
    'scale_down',
    'scale_up',
    'mirror_reverse',
  ]
  const effect = effects[Math.floor(Math.random() * effects.length)]

  if (effect === 'scale_down') {
    // 缩小 0~75% => 实际绘制系数 0.25~1.00
    return {
      effect,
      drawScale: randomInRange(0.25, 1),
      isGold: Math.random() < GOLD_BLOCK_PROBABILITY,
    }
  }

  if (effect === 'scale_up') {
    // 放大 0~50% => 实际绘制系数 1.00~1.50
    return {
      effect,
      drawScale: randomInRange(1, 1.5),
      isGold: Math.random() < GOLD_BLOCK_PROBABILITY,
    }
  }

  return {
    effect,
    drawScale: 1,
    isGold: Math.random() < GOLD_BLOCK_PROBABILITY,
  }
}

const getFloatTextStyle = (item: FloatingTextItem) => {
  return {
    left: `${item.x}%`,
    top: `${item.y}%`,
    transform: `rotate(${item.rotate}deg)`,
    fontSize: `${item.size}px`,
    opacity: item.opacity.toFixed(2),
    animationDelay: `${item.delay}ms`,
    animationDuration: `${item.duration}ms`,
  }
}

const generateFloatingTexts = () => {
  const count = Math.floor(randomInRange(7, 12))
  const items: FloatingTextItem[] = []
  const now = Date.now()
  for (let i = 0; i < count; i += 1) {
    const text = FLOATING_TEXT_POOL[Math.floor(Math.random() * FLOATING_TEXT_POOL.length)]
    items.push({
      id: `${now}-${i}-${Math.random().toString(36).slice(2, 8)}`,
      text,
      x: randomInRange(6, 86),
      y: randomInRange(8, 82),
      rotate: randomInRange(-8, 8),
      size: randomInRange(14, 24),
      delay: randomInRange(0, 2200),
      duration: randomInRange(4200, 7600),
      opacity: randomInRange(0.4, 0.72),
    })
  }
  floatingTexts.value = items
}

const pushSparkBurst = (x: number, y: number, count: number) => {
  const palette = ['#ffd76a', '#ffe8a3', '#fff3d1', '#ffd18a']
  const maxParticleCount = 360
  if (sparkParticles.length > maxParticleCount) {
    sparkParticles.splice(0, sparkParticles.length - maxParticleCount)
  }
  for (let i = 0; i < count; i += 1) {
    const angle = randomInRange(0, Math.PI * 2)
    const speed = randomInRange(90, 320)
    sparkParticles.push({
      x,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed * 0.8,
      life: randomInRange(0.16, 0.4),
      maxLife: randomInRange(0.16, 0.4),
      size: randomInRange(1.2, 3.4),
      color: palette[Math.floor(Math.random() * palette.length)],
    })
  }
}

const updateAndDrawSparks = (deltaSeconds: number) => {
  if (!canvasCtx || sparkParticles.length === 0) return

  const gravity = 760
  const alive: SparkParticle[] = []
  for (const p of sparkParticles) {
    p.life -= deltaSeconds
    if (p.life <= 0) continue

    p.x += p.vx * deltaSeconds
    p.y += p.vy * deltaSeconds
    p.vy += gravity * deltaSeconds

    canvasCtx.globalAlpha = Math.max(0, p.life / p.maxLife) * 0.9
    canvasCtx.fillStyle = p.color
    canvasCtx.beginPath()
    canvasCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
    canvasCtx.fill()
    alive.push(p)
  }
  canvasCtx.globalAlpha = 1
  sparkParticles = alive
}

const triggerShake = (magnitude: number, durationMs: number) => {
  const now = performance.now()
  if (now < shakeEndAt) {
    shakeEndAt = Math.max(shakeEndAt, now + durationMs)
    shakeMagnitude = Math.max(shakeMagnitude, magnitude)
    return
  }

  shakeStartAt = now
  shakeEndAt = now + durationMs
  shakeMagnitude = magnitude
}

const getShakeOffset = (now: number) => {
  if (now >= shakeEndAt) return { x: 0, y: 0 }
  const remainRatio = (shakeEndAt - now) / Math.max(1, shakeEndAt - shakeStartAt)
  const currentMagnitude = shakeMagnitude * remainRatio
  return {
    x: randomInRange(-currentMagnitude, currentMagnitude),
    y: randomInRange(-currentMagnitude * 0.66, currentMagnitude * 0.66),
  }
}

const triggerComboText = () => {
  const now = Date.now()
  collisionHistory = collisionHistory.filter(ts => now - ts <= 900)
  collisionHistory.push(now)

  const comboCount = collisionHistory.length
  if (comboCount < 2) return

  let level = '不错！'
  if (comboCount >= 8) {
    level = '太离谱了！'
  } else if (comboCount >= 6) {
    level = '疯狂连击！'
  } else if (comboCount >= 4) {
    level = '太棒了！'
  }

  comboLabel.value = `x${comboCount} ${level}`
  comboSerial.value += 1

  if (comboHideTimerId !== null) {
    window.clearTimeout(comboHideTimerId)
  }
  comboHideTimerId = window.setTimeout(() => {
    comboLabel.value = ''
  }, 780)
}

const triggerFreezeFlash = () => {
  freezeFlashVisible.value = true
  if (freezeFlashTimerId !== null) {
    window.clearTimeout(freezeFlashTimerId)
  }
  freezeFlashTimerId = window.setTimeout(() => {
    freezeFlashVisible.value = false
  }, 320)
}

const applyWindBurst = () => {
  if (!engine || emergencyStopped) return

  const baseForce = randomInRange(-0.00007, 0.00007)
  if (Math.abs(baseForce) < 0.00001) return

  for (const body of blockBodies) {
    if (body.isSleeping) continue
    Body.applyForce(body, body.position, {
      x: baseForce * randomInRange(0.8, 1.2),
      y: 0,
    })
  }
}

const stopWindSchedule = () => {
  if (windTimerId !== null) {
    window.clearTimeout(windTimerId)
    windTimerId = null
  }
}

const startWindSchedule = () => {
  stopWindSchedule()
  const run = () => {
    if (!engine || emergencyStopped) return
    applyWindBurst()
    windTimerId = window.setTimeout(run, randomInRange(1800, 4200))
  }
  windTimerId = window.setTimeout(run, randomInRange(900, 2200))
}

const collisionStartHandler = (event: any) => {
  if (emergencyStopped || !event?.pairs) return

  for (const pair of event.pairs) {
    const bodyA = pair.bodyA as MatterBody
    const bodyB = pair.bodyB as MatterBody
    const aIsBlock = blockBodyIds.has(bodyA.id)
    const bIsBlock = blockBodyIds.has(bodyB.id)
    if (!aIsBlock && !bIsBlock) continue

    const relativeVelocityX = bodyA.velocity.x - bodyB.velocity.x
    const relativeVelocityY = bodyA.velocity.y - bodyB.velocity.y
    const relativeSpeed = Math.hypot(relativeVelocityX, relativeVelocityY)
    if (relativeSpeed < 1.15) continue

    const hitPoint = pair.collision?.supports?.[0]
    const x = hitPoint?.x ?? (bodyA.position.x + bodyB.position.x) / 2
    const y = hitPoint?.y ?? (bodyA.position.y + bodyB.position.y) / 2
    const sparkCount = Math.floor(Math.max(4, Math.min(16, relativeSpeed * 2.4)))
    pushSparkBurst(x, y, sparkCount)

    if (relativeSpeed >= 2.2) {
      triggerComboText()
    }
    if (relativeSpeed >= 3.7) {
      triggerShake(randomInRange(3, 6), randomInRange(80, 120))
    }
  }
}

const loadLogoImage = () => {
  if (logoImage && logoImage.complete) {
    return Promise.resolve(logoImage)
  }

  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image()
    image.src = '/logo.png'
    image.onload = () => {
      logoImage = image
      resolve(image)
    }
    image.onerror = () => reject(new Error('Failed to load /logo.png'))
  })
}

const syncCanvasSize = () => {
  const canvas = canvasRef.value
  if (!canvas) return

  worldWidth = Math.max(1, Math.floor(canvas.clientWidth))
  worldHeight = Math.max(1, Math.floor(canvas.clientHeight))
  dpr = Math.min(window.devicePixelRatio || 1, 2)

  canvas.width = Math.floor(worldWidth * dpr)
  canvas.height = Math.floor(worldHeight * dpr)

  const context = canvas.getContext('2d')
  if (!context) return
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  canvasCtx = context
}

const rebuildWalls = () => {
  if (!engine) return

  if (borderWalls.length > 0) {
    World.remove(engine.world, borderWalls)
  }

  const wallThickness = safeBlockSize.value * 1.5

  // 仅创建左右与底部边界，上方保持开放以允许堆叠超出可视区
  const leftWall = Bodies.rectangle(
    -wallThickness / 2,
    worldHeight / 2,
    wallThickness,
    worldHeight * 3,
    {
      isStatic: true,
      restitution: 0,
      friction: 0.9,
    }
  )
  const rightWall = Bodies.rectangle(
    worldWidth + wallThickness / 2,
    worldHeight / 2,
    wallThickness,
    worldHeight * 3,
    {
      isStatic: true,
      restitution: 0,
      friction: 0.9,
    }
  )
  const bottomWall = Bodies.rectangle(
    worldWidth / 2,
    worldHeight + wallThickness / 2,
    worldWidth + wallThickness * 2,
    wallThickness,
    {
      isStatic: true,
      restitution: 0,
      friction: 0.95,
    }
  )

  borderWalls = [leftWall, rightWall, bottomWall]
  World.add(engine.world, borderWalls)
}

const spawnBlock = () => {
  if (!engine || emergencyStopped) return

  const variant = pickRandomVisualEffect()
  const size = safeBlockSize.value * variant.drawScale
  const minX = size / 2 + 2
  const maxX = worldWidth - size / 2 - 2
  const x = randomInRange(minX, Math.max(minX + 1, maxX))
  const y = randomInRange(-size * 3.2, -size * 1.1)

  const block = Bodies.rectangle(x, y, size, size, {
    restitution: 0.02,
    friction: 0.85,
    frictionStatic: 0.95,
    frictionAir: 0.03,
    density: 0.0025,
    slop: 0.08,
    sleepThreshold: 40,
  })

  Body.setAngle(block, randomInRange(-0.8, 0.8))
  Body.setAngularVelocity(block, randomInRange(-0.08, 0.08))

  blockVisualEffects.set(block, variant)
  blockBodies.push(block)
  blockBodyIds.add(block.id)
  World.add(engine.world, block)
}

const startSpawning = () => {
  stopSpawning()
  spawnBlock()
  spawnTimerId = window.setInterval(spawnBlock, 110)
}

const stopSpawning = () => {
  if (spawnTimerId !== null) {
    window.clearInterval(spawnTimerId)
    spawnTimerId = null
  }
}

const stabilizeBodies = () => {
  const linearSleepSpeed = 0.05
  const angularSleepSpeed = 0.04
  const angularCap = 0.8

  for (const body of blockBodies) {
    if (body.position.y > safeBlockSize.value * 0.4) {
      enteredViewportBodies.add(body)
    }

    const absAngularVelocity = Math.abs(body.angularVelocity)
    if (absAngularVelocity > angularCap) {
      Body.setAngularVelocity(body, Math.sign(body.angularVelocity) * angularCap)
    }

    if (body.isSleeping) {
      if (absAngularVelocity > 0.001) {
        Body.setAngularVelocity(body, 0)
      }
      continue
    }

    if (body.speed < 0.12 && absAngularVelocity > 0.22) {
      Body.setAngularVelocity(body, body.angularVelocity * 0.85)
    }

    if (body.speed < linearSleepSpeed) {
      Body.setVelocity(body, { x: 0, y: 0 })
    }

    if (absAngularVelocity < angularSleepSpeed && body.speed < 0.08) {
      Body.setAngularVelocity(body, 0)
    }
  }
}

const hasReachedTopBoundary = () => {
  if (worldWidth <= 0 || blockBodies.length === 0) return false

  // 改为“横向大部分区域触顶”判定，避免单列先触顶导致过早停机
  const binCount = Math.max(4, Math.min(14, Math.ceil(worldWidth / safeBlockSize.value)))
  const binWidth = worldWidth / binCount
  const topThresholdY = Math.max(0, safeBlockSize.value * 0.18)
  const coveredBins = new Array<boolean>(binCount).fill(false)

  for (const body of blockBodies) {
    if (!enteredViewportBodies.has(body)) continue
    if (body.bounds.min.y > topThresholdY) continue

    // 过滤高速掠过顶部的瞬时状态，减少误触发
    if (!body.isSleeping && body.speed > 1.2) continue

    const minX = Math.max(0, body.bounds.min.x)
    const maxX = Math.min(worldWidth, body.bounds.max.x)
    if (maxX <= 0 || minX >= worldWidth || maxX <= minX) continue

    const startBin = Math.max(0, Math.floor(minX / binWidth))
    const endBin = Math.min(binCount - 1, Math.floor((maxX - 0.001) / binWidth))
    for (let i = startBin; i <= endBin; i += 1) {
      coveredBins[i] = true
    }
  }

  const coveredCount = coveredBins.reduce((acc, covered) => acc + (covered ? 1 : 0), 0)
  const coverageRatio = coveredCount / binCount

  // 大部分区域触顶（约75%）即停机，允许局部有空隙
  return coverageRatio >= 0.75
}

const drawBlockSprite = (drawSize: number, isGold: boolean) => {
  if (!canvasCtx) return

  if (isGold) {
    canvasCtx.shadowColor = 'rgba(255, 215, 120, 0.9)'
    canvasCtx.shadowBlur = Math.max(12, drawSize * 0.22)
  }

  if (logoImage && logoImage.complete) {
    canvasCtx.drawImage(logoImage, -drawSize / 2, -drawSize / 2, drawSize, drawSize)
  } else {
    canvasCtx.fillStyle = '#f4f4f4'
    canvasCtx.fillRect(-drawSize / 2, -drawSize / 2, drawSize, drawSize)
    canvasCtx.strokeStyle = '#d9d9d9'
    canvasCtx.strokeRect(-drawSize / 2, -drawSize / 2, drawSize, drawSize)
  }

  if (isGold) {
    const prevCompositeOperation = canvasCtx.globalCompositeOperation
    canvasCtx.globalCompositeOperation = 'source-atop'
    canvasCtx.fillStyle = 'rgba(255, 220, 120, 0.34)'
    canvasCtx.fillRect(-drawSize / 2, -drawSize / 2, drawSize, drawSize)
    canvasCtx.globalCompositeOperation = prevCompositeOperation

    canvasCtx.shadowBlur = 0
  }
}

const drawBlockInstance = (
  body: MatterBody,
  variant: VisualVariant,
  alpha: number,
  trailOffsetFactor: number
) => {
  if (!canvasCtx) return

  let scaleX = 1
  let scaleY = 1
  if (variant.effect === 'mirror') {
    scaleX = -1
  } else if (variant.effect === 'mirror_reverse') {
    scaleY = -1
  }

  const drawSize = safeBlockSize.value * variant.drawScale
  canvasCtx.save()
  canvasCtx.globalAlpha = alpha
  canvasCtx.translate(
    body.position.x - body.velocity.x * trailOffsetFactor,
    body.position.y - body.velocity.y * trailOffsetFactor
  )
  canvasCtx.rotate(body.angle - body.angularVelocity * trailOffsetFactor * 0.08)
  canvasCtx.scale(scaleX, scaleY)
  drawBlockSprite(drawSize, variant.isGold)
  canvasCtx.restore()
}

const drawFrame = () => {
  if (!canvasCtx) return

  const now = performance.now()
  if (lastRenderAt === 0) {
    lastRenderAt = now
  }
  const deltaSeconds = Math.min(0.05, (now - lastRenderAt) / 1000)
  lastRenderAt = now

  canvasCtx.clearRect(0, 0, worldWidth, worldHeight)
  const shakeOffset = getShakeOffset(now)
  canvasCtx.save()
  canvasCtx.translate(shakeOffset.x, shakeOffset.y)

  for (const body of blockBodies) {
    const variant = blockVisualEffects.get(body) ?? DEFAULT_VARIANT

    if (!body.isSleeping && body.speed > 0.35) {
      drawBlockInstance(body, variant, 0.14, 10)
      drawBlockInstance(body, variant, 0.09, 18)
    }
    drawBlockInstance(body, variant, 1, 0)
  }

  updateAndDrawSparks(deltaSeconds)
  canvasCtx.restore()
}

const stopAnimationLoop = () => {
  if (animationFrameId !== null) {
    window.cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

const startAnimationLoop = () => {
  stopAnimationLoop()

  const tick = () => {
    if (!engine || emergencyStopped) return

    Engine.update(engine, 1000 / 60)
    drawFrame()
    animationFrameId = window.requestAnimationFrame(tick)
  }

  animationFrameId = window.requestAnimationFrame(tick)
}

const emergencyStop = () => {
  if (!engine || emergencyStopped) return
  emergencyStopped = true

  stopSpawning()
  stopWindSchedule()

  // 触顶时立即冻结全部刚体，杜绝后续挤压抖动与空转
  for (const body of blockBodies) {
    Body.setVelocity(body, { x: 0, y: 0 })
    Body.setAngularVelocity(body, 0)
    Body.setStatic(body, true)
  }

  stopAnimationLoop()
  drawFrame()
  triggerFreezeFlash()
  emit('stopped')
  emit('onStopped')
}

const destroyPhysics = () => {
  stopSpawning()
  stopAnimationLoop()
  stopWindSchedule()

  if (engine) {
    Events.off(engine, 'afterUpdate', afterUpdateHandler)
    Events.off(engine, 'collisionStart', collisionStartHandler)
    Composite.clear(engine.world, false, true)
    Engine.clear(engine)
  }

  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
    resizeHandler = null
  }

  engine = null
  canvasCtx = null
  borderWalls = []
  blockBodies = []
  blockBodyIds = new Set<number>()
  enteredViewportBodies = new WeakSet<MatterBody>()
  blockVisualEffects = new WeakMap<MatterBody, VisualVariant>()
  sparkParticles = []
  collisionHistory = []
  lastRenderAt = 0
  shakeStartAt = 0
  shakeEndAt = 0
  shakeMagnitude = 0
  comboLabel.value = ''
  floatingTexts.value = []
  freezeFlashVisible.value = false

  if (comboHideTimerId !== null) {
    window.clearTimeout(comboHideTimerId)
    comboHideTimerId = null
  }
  if (freezeFlashTimerId !== null) {
    window.clearTimeout(freezeFlashTimerId)
    freezeFlashTimerId = null
  }

  emergencyStopped = false
}

const initPhysics = async () => {
  await nextTick()
  destroyPhysics()

  const canvas = canvasRef.value
  if (!canvas) return

  syncCanvasSize()

  try {
    await loadLogoImage()
  } catch {
    // logo 加载失败时退化为纯色方块，不影响交互与停机逻辑
  }

  engine = Engine.create({
    enableSleeping: true,
    positionIterations: 10,
    velocityIterations: 8,
    constraintIterations: 4,
    gravity: {
      x: 0,
      y: 1,
      scale: 0.0018,
    },
  })

  rebuildWalls()
  Events.on(engine, 'afterUpdate', afterUpdateHandler)
  Events.on(engine, 'collisionStart', collisionStartHandler)

  resizeHandler = () => {
    syncCanvasSize()
    rebuildWalls()
  }
  window.addEventListener('resize', resizeHandler, { passive: true })

  generateFloatingTexts()
  startWindSchedule()
  startSpawning()
  startAnimationLoop()
}

const closeMask = () => {
  emit('update:modelValue', false)
  emit('update:visible', false)
  destroyPhysics()
}

const handleMaskClick = () => {
  closeMask()
}

watch(
  isOpen,
  open => {
    if (open) {
      void initPhysics()
    } else {
      destroyPhysics()
    }
  },
  { immediate: true }
)

watch(
  () => props.blockSize,
  () => {
    if (!isOpen.value) return
    void initPhysics()
  }
)

onBeforeUnmount(() => {
  destroyPhysics()
})
</script>

<style scoped>
.overlay-rain-mask {
  position: fixed;
  inset: 0;
  z-index: 2147483000;
  cursor: pointer;
}

.overlay-rain-mask__canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.overlay-rain-mask__exit-hint {
  position: absolute;
  top: 16px;
  right: 18px;
  z-index: 2;
  pointer-events: none;
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}

.overlay-rain-mask__float-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.overlay-rain-mask__float-text {
  position: absolute;
  display: inline-block;
  color: rgba(255, 255, 255, 0.58);
  font-weight: 700;
  letter-spacing: 1px;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.45);
  white-space: nowrap;
  animation-name: overlay-float-drift;
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
  animation-direction: alternate;
}

.overlay-rain-mask__combo {
  position: absolute;
  top: 26px;
  left: 26px;
  pointer-events: none;
  color: #ffd76a;
  font-size: clamp(24px, 3vw, 44px);
  font-weight: 800;
  letter-spacing: 1.5px;
  text-shadow: 0 2px 10px rgba(255, 172, 64, 0.35);
  animation: overlay-combo-pop 0.78s ease-out;
}

.overlay-rain-mask__freeze-flash {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: #ffffff;
  animation: overlay-freeze-flash 0.32s ease-out forwards;
}

@keyframes overlay-float-drift {
  0% {
    transform: translateY(0px) translateX(0px) rotate(-2deg);
  }
  100% {
    transform: translateY(-16px) translateX(8px) rotate(2deg);
  }
}

@keyframes overlay-combo-pop {
  0% {
    opacity: 0;
    transform: translateY(12px) scale(0.9);
  }
  20% {
    opacity: 1;
    transform: translateY(0) scale(1.04);
  }
  100% {
    opacity: 0;
    transform: translateY(-14px) scale(0.98);
  }
}

@keyframes overlay-freeze-flash {
  0% {
    opacity: 0;
  }
  12% {
    opacity: 0.85;
  }
  100% {
    opacity: 0;
  }
}
</style>
