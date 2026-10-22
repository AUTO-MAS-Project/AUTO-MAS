<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { DesktopMascotData, DesktopMascotUpdate } from '@/types/desktopMascot'
import { useDesktopMascotPlayback } from '@/composables/useDesktopMascotPlayback'

const data = ref<DesktopMascotData | null>(null)
const dragging = ref(false)
const lookFrame = ref<number | null>(null)
const noticeElement = ref<HTMLElement>()
const noticeWidth = ref(0)
const viewportWidth = ref(window.innerWidth)
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
const reducedMotion = ref(motionPreference.matches)
let dispose: (() => void) | undefined
let disposeUpdate: (() => void) | undefined
let disposeLook: (() => void) | undefined
let activePointerId: number | null = null
let pointerTarget: HTMLElement | null = null
let dragRevision = 0
let noticeObserver: ResizeObserver | undefined
let press: { screenX: number; screenY: number; x: number; y: number; revision: number } | null =
  null
let dragRequested = false
let clickAnimation: Animation | undefined
let mounted = true
const DRAG_THRESHOLD = 5
const { sprite, stopped } = useDesktopMascotPlayback(data, dragging, lookFrame, reducedMotion)

const isIdleMessage = computed(
  () =>
    !data.value?.notice && data.value?.state === 'idle' && Boolean(data.value?.idleMessage?.text)
)
const noticeText = computed(
  () => data.value?.notice || (isIdleMessage.value ? data.value?.idleMessage?.text : undefined)
)

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

const noticeStyle = computed(() => {
  if (!data.value) return {}
  const {
    width,
    height,
    offsetX,
    offsetY,
    noticeBelow,
    noticeWidth: maxNoticeWidth,
    noticeHeight,
    colors,
  } = data.value
  const anchor = offsetX + width / 2
  const boxWidth = noticeWidth.value || maxNoticeWidth
  const left = Math.max(0, Math.min(anchor - boxWidth / 2, viewportWidth.value - boxWidth))
  const arrow = anchor - left
  const leftRadius = Math.max(0, Math.min(colors.radius, arrow - 5))
  const rightRadius = Math.max(0, Math.min(colors.radius, boxWidth - arrow - 5))
  return {
    left: `${left}px`,
    maxWidth: `${maxNoticeWidth}px`,
    maxHeight: `${Math.max(0, noticeHeight - 12)}px`,
    '--mascot-notice-arrow-x': `${arrow - 1}px`,
    top: noticeBelow ? `${offsetY + height + 12}px` : undefined,
    bottom: noticeBelow ? undefined : `${height + 12}px`,
    '--mascot-notice-content-height': `${Math.max(0, noticeHeight - 38 - (isIdleMessage.value && data.value.idleMessage?.author && noticeHeight >= 78 ? 20 : 0))}px`,
    '--ant-color-bg-elevated': colors.background,
    '--ant-color-text': colors.text,
    '--ant-color-border': colors.border,
    borderRadius: noticeBelow
      ? `${leftRadius}px ${rightRadius}px ${colors.radius}px ${colors.radius}px`
      : `${colors.radius}px ${colors.radius}px ${rightRadius}px ${leftRadius}px`,
  }
})

watch(
  noticeElement,
  element => {
    noticeObserver?.disconnect()
    if (!element) return
    measureNotice()
    noticeObserver = new ResizeObserver(measureNotice)
    noticeObserver.observe(element)
  },
  { flush: 'post' }
)

onMounted(async () => {
  window.addEventListener('resize', updateViewportWidth)
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
  if (!changed && mounted) {
    data.value = initial ? { ...initial, ...pendingUpdate } : null
    lookFrame.value = initial?.lookFrame ?? null
  }
})

onUnmounted(() => {
  dispose?.()
  disposeUpdate?.()
  disposeLook?.()
  mounted = false
  clickAnimation?.cancel()
  noticeObserver?.disconnect()
  window.removeEventListener('resize', updateViewportWidth)
  motionPreference.removeEventListener('change', updateMotionPreference)
  endDrag()
})

function measureNotice(): void {
  noticeWidth.value = noticeElement.value?.getBoundingClientRect().width ?? 0
}

function updateViewportWidth(): void {
  viewportWidth.value = window.innerWidth
}

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
  if (activePointerId === null) window.desktopMascotAPI?.pointer('hover')
}

function startPointer(event: PointerEvent): void {
  if (event.button !== 0 || activePointerId !== null) return
  const api = window.desktopMascotAPI
  if (!api || !data.value) return
  event.preventDefault()
  const target = event.currentTarget as HTMLElement
  const bounds = target.getBoundingClientRect()
  activePointerId = event.pointerId
  pointerTarget = target
  dragRevision++
  dragRequested = false
  press = {
    screenX: event.screenX,
    screenY: event.screenY,
    x: event.clientX - bounds.left,
    y: event.clientY - bounds.top,
    revision: data.value.revision,
  }
  clickAnimation?.cancel()
  target.setPointerCapture(event.pointerId)
}

async function startDrag(): Promise<void> {
  if (!press || dragRequested) return
  const api = window.desktopMascotAPI
  const revision = dragRevision
  dragRequested = true
  try {
    const accepted = await api.startDrag({
      x: press.x,
      y: press.y,
      session: revision,
      revision: press.revision,
    })
    if (revision !== dragRevision) {
      if (accepted) api.pointer('end', revision)
      return
    }
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
  else if (
    press &&
    Math.hypot(event.screenX - press.screenX, event.screenY - press.screenY) >= DRAG_THRESHOLD
  )
    void startDrag()
}

function releasePointer(event: PointerEvent): void {
  if (event.pointerId !== activePointerId) return
  const clicked =
    press &&
    !dragRequested &&
    data.value?.revision === press.revision &&
    Math.hypot(event.screenX - press.screenX, event.screenY - press.screenY) < DRAG_THRESHOLD
  const target = pointerTarget
  endDrag(event)
  if (
    clicked &&
    target &&
    data.value?.animate &&
    (!reducedMotion.value || data.value.motionOverride)
  ) {
    clickAnimation?.cancel()
    clickAnimation = target.animate(
      [
        { transform: 'scale(1)' },
        { transform: 'scale(1.06, 0.94)' },
        { transform: 'scale(0.98, 1.02)' },
        { transform: 'scale(1)' },
      ],
      { duration: 240, easing: 'ease-out' }
    )
  }
}

function endDrag(event?: PointerEvent): void {
  if (activePointerId === null || (event && event.pointerId !== activePointerId)) return
  const pointerId = activePointerId
  const target = pointerTarget
  const session = dragRevision
  activePointerId = null
  pointerTarget = null
  press = null
  const requested = dragRequested
  dragRequested = false
  dragRevision++
  dragging.value = false
  if (target?.hasPointerCapture(pointerId)) target.releasePointerCapture(pointerId)
  if (requested) window.desktopMascotAPI?.pointer('end', session)
}
</script>

<template>
  <div v-if="data" class="desktop-mascot" @mousemove="hover" @mouseleave="hover">
    <div
      v-if="noticeText && data.noticeHeight >= 58"
      ref="noticeElement"
      class="mascot-notice"
      :class="{ 'idle-message': isIdleMessage, 'notice-below': data.noticeBelow }"
      :style="noticeStyle"
      role="status"
    >
      <span>{{ noticeText }}</span>
      <small
        v-if="isIdleMessage && data.idleMessage?.author && data.noticeHeight >= 78"
        class="mascot-notice-author"
        >—— {{ data.idleMessage.author }}</small
      >
    </div>
    <div
      class="mascot-avatar"
      :class="{
        dragging,
        stopped,
        'reduced-motion': (reducedMotion && !data.motionOverride) || !data.animate,
      }"
      :style="avatarStyle"
      @pointerdown="startPointer"
      @pointermove="moveDrag"
      @pointerup="releasePointer"
      @pointercancel="endDrag"
      @lostpointercapture="endDrag"
    >
      <div v-if="data.animation && sprite" class="mascot-sprite">
        <img :src="sprite.imageUrl" :style="sprite.style" draggable="false" alt="" />
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
  width: max-content;
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
  max-height: var(--mascot-notice-content-height);
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
  left: var(--mascot-notice-arrow-x);
  bottom: -5px;
  width: 8px;
  height: 8px;
  border-right: 1px solid var(--ant-color-border);
  border-bottom: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-elevated);
  content: '';
  transform: translateX(-50%) rotate(45deg);
}

.mascot-notice.notice-below::after {
  top: -5px;
  bottom: auto;
  transform: translateX(-50%) rotate(225deg);
}
</style>
