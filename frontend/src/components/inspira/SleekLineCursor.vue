<template>
  <canvas
    id="canvas"
    ref="canvasRef"
    :class="['sleek-line-cursor', props.class]"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, withDefaults } from 'vue'

interface SleekLineCursorProps {
  friction?: number
  trails?: number
  size?: number
  dampening?: number
  tension?: number
  class?: string
}

const props = withDefaults(defineProps<SleekLineCursorProps>(), {
  friction: 0.5,
  trails: 20,
  size: 50,
  dampening: 0.25,
  tension: 0.98,
  class: undefined,
})

class Oscillator {
  phase = 0
  offset = 0
  frequency = 0.001
  amplitude = 1
  currentValue = 0

  constructor(options: Partial<Oscillator> = {}) {
    this.phase = options.phase ?? 0
    this.offset = options.offset ?? 0
    this.frequency = options.frequency ?? 0.001
    this.amplitude = options.amplitude ?? 1
  }

  update() {
    this.phase += this.frequency
    this.currentValue = this.offset + Math.sin(this.phase) * this.amplitude
    return this.currentValue
  }
}

class CursorNode {
  x = 0
  y = 0
  vx = 0
  vy = 0
}

class CursorLine {
  spring = 0
  friction = 0
  nodes: CursorNode[] = []

  constructor(spring: number) {
    this.spring = spring + 0.1 * Math.random() - 0.02
    this.friction = props.friction + 0.01 * Math.random() - 0.002
    this.nodes = Array.from({ length: props.size }, () => {
      const node = new CursorNode()
      node.x = pointer.x
      node.y = pointer.y
      return node
    })
  }

  update() {
    let spring = this.spring
    let node = this.nodes[0]

    node.vx += (pointer.x - node.x) * spring
    node.vy += (pointer.y - node.y) * spring

    for (let index = 0; index < this.nodes.length; index += 1) {
      node = this.nodes[index]

      if (index > 0) {
        const previousNode = this.nodes[index - 1]
        node.vx += (previousNode.x - node.x) * spring
        node.vy += (previousNode.y - node.y) * spring
        node.vx += previousNode.vx * props.dampening
        node.vy += previousNode.vy * props.dampening
      }

      node.vx *= this.friction
      node.vy *= this.friction
      node.x += node.vx
      node.y += node.vy
      spring *= props.tension
    }
  }

  draw(context: CanvasRenderingContext2D) {
    let node: CursorNode
    let nextNode: CursorNode
    let midpointX = this.nodes[0].x
    let midpointY = this.nodes[0].y

    context.beginPath()
    context.moveTo(midpointX, midpointY)

    for (let index = 1; index < this.nodes.length - 2; index += 1) {
      node = this.nodes[index]
      nextNode = this.nodes[index + 1]
      midpointX = 0.5 * (node.x + nextNode.x)
      midpointY = 0.5 * (node.y + nextNode.y)
      context.quadraticCurveTo(node.x, node.y, midpointX, midpointY)
    }

    node = this.nodes[this.nodes.length - 2]
    nextNode = this.nodes[this.nodes.length - 1]
    context.quadraticCurveTo(node.x, node.y, nextNode.x, nextNode.y)
    context.stroke()
    context.closePath()
  }
}

const canvasRef = ref<HTMLCanvasElement | null>(null)
const pointer = { x: 0, y: 0 }
const lines: CursorLine[] = []

let canvasContext: CanvasRenderingContext2D | null = null
let colorOscillator: Oscillator | null = null
let animationFrameId: number | null = null
let running = false

function createLines() {
  lines.length = 0
  for (let index = 0; index < props.trails; index += 1) {
    lines.push(new CursorLine(0.4 + (index / props.trails) * 0.025))
  }
}

function updatePointer(event: MouseEvent | TouchEvent) {
  if ('touches' in event) {
    const touch = event.touches[0]
    if (!touch) {
      return
    }

    pointer.x = touch.pageX
    pointer.y = touch.pageY
  } else {
    pointer.x = event.clientX
    pointer.y = event.clientY
  }

  event.preventDefault()
}

function handleTouchStart(event: TouchEvent) {
  if (event.touches.length === 1) {
    pointer.x = event.touches[0].pageX
    pointer.y = event.touches[0].pageY
  }
}

function render() {
  if (!running || !canvasContext || !colorOscillator) {
    return
  }

  canvasContext.globalCompositeOperation = 'source-over'
  canvasContext.clearRect(0, 0, canvasContext.canvas.width, canvasContext.canvas.height)
  canvasContext.globalCompositeOperation = 'lighter'
  canvasContext.strokeStyle = `hsla(${Math.round(colorOscillator.update())},50%,50%,0.2)`
  canvasContext.lineWidth = 1

  for (const line of lines) {
    line.update()
    line.draw(canvasContext)
  }

  animationFrameId = window.requestAnimationFrame(render)
}

function startRendering() {
  running = true
  if (animationFrameId === null) {
    animationFrameId = window.requestAnimationFrame(render)
  }
}

function resizeCanvas() {
  const canvas = canvasRef.value
  if (!canvas) {
    return
  }

  canvas.width = Math.max(window.innerWidth - 20, 1)
  canvas.height = Math.max(window.innerHeight, 1)
}

function handleInitialPointer(event: MouseEvent | TouchEvent) {
  document.removeEventListener('mousemove', handleInitialPointer)
  document.removeEventListener('touchstart', handleInitialPointer)
  document.addEventListener('mousemove', updatePointer)
  document.addEventListener('touchmove', updatePointer)
  document.addEventListener('touchstart', handleTouchStart)
  updatePointer(event)
  createLines()
  startRendering()
}

function handleFocus() {
  startRendering()
}

function stopRendering() {
  running = false
  if (animationFrameId !== null) {
    window.cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) {
    return
  }

  canvasContext = canvas.getContext('2d')
  if (!canvasContext) {
    return
  }

  colorOscillator = new Oscillator({
    phase: Math.random() * Math.PI * 2,
    amplitude: 85,
    frequency: 0.0015,
    offset: 285,
  })

  document.addEventListener('mousemove', handleInitialPointer)
  document.addEventListener('touchstart', handleInitialPointer)
  document.body.addEventListener('orientationchange', resizeCanvas)
  window.addEventListener('resize', resizeCanvas)
  window.addEventListener('focus', handleFocus)
  window.addEventListener('blur', handleFocus)
  resizeCanvas()
})

onUnmounted(() => {
  stopRendering()
  document.removeEventListener('mousemove', handleInitialPointer)
  document.removeEventListener('mousemove', updatePointer)
  document.removeEventListener('touchstart', handleInitialPointer)
  document.removeEventListener('touchstart', handleTouchStart)
  document.removeEventListener('touchmove', updatePointer)
  document.body.removeEventListener('orientationchange', resizeCanvas)
  window.removeEventListener('resize', resizeCanvas)
  window.removeEventListener('focus', handleFocus)
  window.removeEventListener('blur', handleFocus)
  canvasContext = null
  colorOscillator = null
  lines.length = 0
})
</script>

<style scoped>
.sleek-line-cursor {
  position: fixed;
  inset: 0;
  z-index: 50;
  width: 100vw;
  height: 100vh;
  display: block;
  pointer-events: none;
}
</style>
