<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { DesktopMascotData, DesktopMascotUpdate } from '@/types/desktopMascot'

const data = ref<DesktopMascotData | null>(null)
const frame = ref(0)
const dragging = ref(false)
const lookFrame = ref<number | null>(null)
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
const reducedMotion = ref(motionPreference.matches)
let dispose: (() => void) | undefined
let disposeUpdate: (() => void) | undefined
let disposeLook: (() => void) | undefined
let frameTimer: ReturnType<typeof setInterval> | undefined
let activePointerId: number | null = null
let pointerTarget: HTMLElement | null = null
let dragRevision = 0

const isIdleMessage = computed(
  () =>
    !data.value?.notice && data.value?.state === 'idle' && Boolean(data.value?.idleMessage?.text)
)
const noticeText = computed(
  () => data.value?.notice || (isIdleMessage.value ? data.value?.idleMessage?.text : undefined)
)

const stopped = computed(() => !dragging.value && data.value?.reaction === 'stopped')
const reacting = computed(
  () =>
    !dragging.value &&
    Boolean(data.value?.reaction && data.value.reaction !== 'stopped') &&
    Boolean(data.value?.animation?.resultImageUrl)
)
const looking = computed(
  () =>
    !dragging.value &&
    !data.value?.reaction &&
    data.value?.state === 'idle' &&
    lookFrame.value !== null &&
    Boolean(data.value.animation?.lookImageUrl)
)
const dragSprite = computed(() => dragging.value && Boolean(data.value?.animation?.dragImageUrl))
const spriteImageUrl = computed(() => {
  const animation = data.value?.animation
  return dragSprite.value
    ? animation?.dragImageUrl
    : reacting.value
      ? animation?.resultImageUrl
      : looking.value
        ? animation?.lookImageUrl
        : animation?.imageUrl
})

const avatarStyle = computed(() => {
  if (!data.value) return {}
  const { width, height, offsetX, offsetY, opacity, colors } = data.value
  return {
    width: `${width}px`,
    height: `${height}px`,
    left: `${offsetX}px`,
    top: `${offsetY}px`,
    opacity,
    '--ant-color-bg-elevated': colors.background,
    '--ant-color-text': colors.text,
    '--ant-color-border': colors.border,
  }
})

const spriteStyle = computed(() => {
  if (!data.value?.animation) return {}
  const { animation, state, reaction } = data.value
  const columns = looking.value ? 3 : animation.columns
  const rows = dragSprite.value ? 1 : looking.value ? 3 : 2
  const column = looking.value
    ? lookFrame.value! % 3
    : stopped.value
      ? Math.min(2, animation.columns - 1)
      : frame.value
  const row = looking.value
    ? Math.floor(lookFrame.value! / 3)
    : reacting.value
      ? reaction === 'success'
        ? 1
        : 0
      : stopped.value || (!dragging.value && state === 'working')
        ? 1
        : 0
  return {
    width: `${columns * 100}%`,
    height: `${rows * 100}%`,
    transform: `translate(${(-column / columns) * 100}%, ${(-row / rows) * 100}%)`,
  }
})

const noticeStyle = computed(() => {
  if (!data.value) return {}
  const { height, offsetY, noticeBelow, colors } = data.value
  return {
    top: noticeBelow ? `${offsetY + height + 12}px` : undefined,
    bottom: noticeBelow ? undefined : `${height + 12}px`,
    '--ant-color-bg-elevated': colors.background,
    '--ant-color-text': colors.text,
    '--ant-color-border': colors.border,
    borderRadius: `${colors.radius}px`,
  }
})

watch(
  () =>
    [
      data.value?.animation,
      data.value?.state,
      dragging.value,
      lookFrame.value,
      data.value?.reaction,
    ] as const,
  () => {
    frame.value = 0
  }
)

watch(
  () =>
    [
      data.value?.animation,
      data.value?.state,
      data.value?.animate,
      reducedMotion.value && !data.value?.motionOverride,
      dragging.value,
      lookFrame.value,
      data.value?.reaction,
      data.value?.fps,
    ] as const,
  ([animation, state, animate, reduced, isDragging, look, reaction, customFps]) => {
    clearInterval(frameTimer)
    if (!animation || !animate || reduced) return
    if (!isDragging && reaction === 'stopped') return
    if (!isDragging && !reaction && state === 'idle' && look !== null && animation.lookImageUrl)
      return
    const fps =
      customFps ??
      (isDragging || reaction || state === 'working' ? animation.workingFps : animation.idleFps)
    frameTimer = setInterval(() => {
      frame.value = (frame.value + 1) % animation.columns
    }, 1000 / fps)
  }
)

onMounted(async () => {
  motionPreference.addEventListener('change', updateMotionPreference)
  const api = window.desktopMascotAPI
  if (!api) return
  let changed = false
  let pendingUpdate: DesktopMascotUpdate = {}
  dispose = api.onChanged(value => {
    endDrag()
    changed = true
    data.value = value
    lookFrame.value = value.lookFrame ?? null
    pendingUpdate = {}
  })
  disposeUpdate = api.onUpdated(update => {
    if (update.dragging === false && update.dragSession === dragRevision) endDrag()
    if (data.value) Object.assign(data.value, update)
    else Object.assign(pendingUpdate, update)
  })
  disposeLook = api.onLookChanged(value => {
    lookFrame.value = value
  })
  const initial = await api.getData()
  if (!changed) {
    data.value = initial ? { ...initial, ...pendingUpdate } : null
    lookFrame.value = initial?.lookFrame ?? null
  }
})

onUnmounted(() => {
  dispose?.()
  disposeUpdate?.()
  disposeLook?.()
  clearInterval(frameTimer)
  motionPreference.removeEventListener('change', updateMotionPreference)
  endDrag()
})

function updateMotionPreference(event: MediaQueryListEvent): void {
  reducedMotion.value = event.matches
}

function decodeStaticImage(event: Event): void {
  const current = data.value
  const image = event.currentTarget as HTMLImageElement
  if (!current?.needsImageDecode || image.src !== current.imageUrl) return
  // nativeImage 不支持 WebP；只在载入时借用浏览器解码，命中图交给主进程缓存。
  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  const context = canvas.getContext('2d')
  if (!context) return
  context.drawImage(image, 0, 0)
  window.desktopMascotAPI.imageDecoded(current.imageUrl, canvas.toDataURL('image/png'))
}

function hover(): void {
  if (!dragging.value) window.desktopMascotAPI?.pointer('hover')
}

async function startDrag(event: PointerEvent): Promise<void> {
  if (event.button !== 0 || activePointerId !== null) return
  const api = window.desktopMascotAPI
  if (!api) return
  event.preventDefault()
  const target = event.currentTarget as HTMLElement
  const bounds = target.getBoundingClientRect()
  activePointerId = event.pointerId
  pointerTarget = target
  const revision = ++dragRevision
  target.setPointerCapture(event.pointerId)
  try {
    const accepted = await api.startDrag({
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
      session: revision,
    })
    if (revision !== dragRevision) return
    if (!accepted) {
      endDrag()
      return
    }
    dragging.value = true
    api.pointer('move', revision)
  } catch {
    if (revision === dragRevision) endDrag()
  }
}

function moveDrag(event: PointerEvent): void {
  if (event.pointerId !== activePointerId) return
  if (event.buttons === 0) endDrag(event)
  else if (dragging.value) window.desktopMascotAPI?.pointer('move', dragRevision)
}

function endDrag(event?: PointerEvent): void {
  if (activePointerId === null || (event && event.pointerId !== activePointerId)) return
  const pointerId = activePointerId
  const target = pointerTarget
  const session = dragRevision
  activePointerId = null
  pointerTarget = null
  dragRevision++
  dragging.value = false
  if (target?.hasPointerCapture(pointerId)) target.releasePointerCapture(pointerId)
  window.desktopMascotAPI?.pointer('end', session)
}
</script>

<template>
  <div v-if="data" class="desktop-mascot" @mousemove="hover" @mouseleave="hover">
    <div
      v-if="noticeText"
      class="mascot-notice"
      :class="{ 'idle-message': isIdleMessage, 'notice-below': data.noticeBelow }"
      :style="noticeStyle"
      role="status"
    >
      <span>{{ noticeText }}</span>
      <small v-if="isIdleMessage && data.idleMessage?.author" class="mascot-notice-author"
        >—— {{ data.idleMessage.author }}</small
      >
    </div>
    <div
      class="mascot-avatar"
      :class="{
        dragging,
        'drag-sprite': dragSprite,
        stopped,
        'reduced-motion': (reducedMotion && !data.motionOverride) || !data.animate,
      }"
      :style="avatarStyle"
      @pointerdown="startDrag"
      @pointermove="moveDrag"
      @pointerup="endDrag"
      @pointercancel="endDrag"
      @lostpointercapture="endDrag"
    >
      <div v-if="data.animation" class="mascot-sprite">
        <img :src="spriteImageUrl" :style="spriteStyle" draggable="false" alt="" />
      </div>
      <img
        v-else
        class="mascot-static-image"
        :src="data.imageUrl"
        draggable="false"
        alt=""
        @load="decodeStaticImage"
      />
    </div>
  </div>
</template>

<style scoped>
.desktop-mascot {
  position: relative;
  width: 100%;
  height: 100%;
  user-select: none;
}

.mascot-avatar {
  position: absolute;
  cursor: grab;
  touch-action: none;
}

.mascot-avatar.dragging {
  cursor: grabbing;
}

.mascot-avatar.stopped {
  animation: mascot-stopped 1200ms steps(1, end) infinite;
}

.mascot-avatar.stopped.reduced-motion {
  animation: none;
}

.mascot-avatar.stopped::after {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 26px;
  height: 30px;
  border: 1px solid var(--ant-color-border);
  border-radius: 50%;
  background: var(--ant-color-bg-elevated);
  color: var(--ant-color-text);
  content: '?';
  font: bold 24px/30px sans-serif;
  text-align: center;
  transform: rotate(12deg);
  pointer-events: none;
}

@keyframes mascot-stopped {
  0%,
  55%,
  100% {
    transform: none;
  }
  58%,
  62% {
    transform: translateX(-2px) rotate(-1deg);
  }
  60%,
  64% {
    transform: translateX(1px) rotate(1deg);
  }
}

.mascot-sprite {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.mascot-sprite img {
  display: block;
  max-width: none;
}

.mascot-static-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}

.mascot-notice {
  position: absolute;
  right: 0;
  max-width: 100%;
  box-sizing: border-box;
  padding: 12px;
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-elevated);
  color: var(--ant-color-text);
  font:
    14px/20px 'Microsoft YaHei',
    sans-serif;
  overflow-wrap: anywhere;
  pointer-events: none;
}

.mascot-notice span {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.mascot-notice.idle-message span {
  -webkit-line-clamp: 2;
}

.mascot-notice-author {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  font-size: 12px;
  line-height: 16px;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mascot-notice::after {
  position: absolute;
  right: 64px;
  bottom: -5px;
  width: 8px;
  height: 8px;
  border-right: 1px solid var(--ant-color-border);
  border-bottom: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-elevated);
  content: '';
  transform: rotate(45deg);
}

.mascot-notice.notice-below::after {
  top: -5px;
  bottom: auto;
  transform: rotate(225deg);
}
</style>
