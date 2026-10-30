import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import type { DesktopMascotData } from '@/types/desktopMascot'

const STATIC_REACTION_DURATION = 1200

interface MascotClip {
  url: string
  mode: 'idle' | 'working' | 'look' | 'drag' | 'reaction' | 'stopped'
  columns: number
  rows: number
  count: number
  action: number
  fps: number
  look: number | null
  reactionId?: number
}

/** 图片准备好后再换动作；播放时钟和气泡生命周期互不依赖。 */
export function useDesktopMascotPlayback(
  data: Ref<DesktopMascotData | null>,
  dragging: Ref<boolean>,
  lookFrame: Ref<number | null>,
  reducedMotion: Ref<boolean>
) {
  const clip = shallowRef<MascotClip | null>(null)
  const frame = ref(0)
  const hidden = ref(document.hidden)
  const decoded = new Set<string>()
  const phases = { idle: 0, working: 0 }
  const stopped = computed(() => !dragging.value && data.value?.reaction === 'stopped')
  let reactionPhase: { id?: number; progress: number } | null = null
  let progress = 0
  let sourceUrl: string | undefined
  let disposed = false

  const desired = computed<MascotClip | null>(() => {
    const value = data.value
    const animation = value?.animation
    if (!value || !animation) return null
    const reaction = !dragging.value && value.reaction
    const look =
      !dragging.value && !reaction && value.state === 'idle' && animation.lookImageUrl
        ? lookFrame.value
        : null
    const drag = dragging.value && animation.dragImageUrl
    const mode: MascotClip['mode'] = dragging.value
      ? 'drag'
      : reaction === 'stopped'
        ? 'stopped'
        : reaction && animation.resultImageUrl
          ? 'reaction'
          : look !== null
            ? 'look'
            : value.state
    return {
      url: drag
        ? animation.dragImageUrl!
        : mode === 'reaction'
          ? animation.resultImageUrl!
          : mode === 'look'
            ? animation.lookImageUrl!
            : animation.imageUrl,
      mode,
      columns: mode === 'look' ? 3 : animation.columns,
      rows:
        mode === 'look' ? 3 : Math.ceil(animation.frameCount / animation.columns) * (drag ? 1 : 2),
      count: animation.frameCount,
      action:
        mode === 'look' || mode === 'drag'
          ? 0
          : mode === 'reaction'
            ? reaction === 'success'
              ? 1
              : 0
            : mode === 'stopped' || value.state === 'working'
              ? 1
              : 0,
      fps:
        value.fps ??
        (dragging.value || reaction ? animation.workingFps : animation[`${value.state}Fps`]),
      look,
      reactionId: mode === 'reaction' || mode === 'stopped' ? value.reactionId : undefined,
    }
  })

  watch(
    () => data.value?.animation,
    () => {
      decoded.clear()
    },
    { flush: 'sync' }
  )
  watch(
    desired,
    (next, _previous, onCleanup) => {
      let stale = false
      onCleanup(() => {
        stale = true
      })
      const commit = () => {
        if (!stale && !disposed) clip.value = next
      }
      if (!next || decoded.has(next.url)) {
        commit()
        return
      }
      const image = new Image()
      image.src = next.url
      void image
        .decode()
        .then(() => {
          if (stale || disposed) return
          decoded.add(next.url)
          commit()
        })
        .catch(() => {
          // 保留上一张可用图片，失败的结果动作不能阻塞后续状态。
          if (!stale && !disposed && next.reactionId !== undefined)
            window.desktopMascotAPI?.reactionEnded(next.reactionId)
        })
    },
    { immediate: true, flush: 'sync' }
  )
  watch(
    clip,
    (next, previous) => {
      if (previous?.mode === 'idle' || previous?.mode === 'working')
        phases[previous.mode] = progress
      if (previous?.mode === 'reaction') reactionPhase = { id: previous.reactionId, progress }
      if (sourceUrl !== data.value?.animation?.imageUrl) {
        sourceUrl = data.value?.animation?.imageUrl
        phases.idle = phases.working = 0
        reactionPhase = null
      }
      if (
        next?.url === previous?.url &&
        next?.mode === previous?.mode &&
        next?.action === previous?.action &&
        next?.reactionId === previous?.reactionId
      )
        return
      progress =
        next?.mode === 'idle' || next?.mode === 'working'
          ? phases[next.mode]
          : next?.mode === 'reaction' && reactionPhase && next.reactionId === reactionPhase.id
            ? reactionPhase.progress
            : 0
      frame.value = Math.floor(progress) % (next?.count || 1)
    },
    { flush: 'sync' }
  )

  const motionDisabled = computed(
    () => !data.value?.animate || (reducedMotion.value && !data.value?.motionOverride)
  )
  watch(
    () => [data.value?.reaction, data.value?.reactionId, data.value?.animation] as const,
    ([reaction, id, animation]) => {
      if (id !== undefined && reaction && reaction !== 'stopped' && !animation?.resultImageUrl)
        window.desktopMascotAPI?.reactionEnded(id)
    },
    { immediate: true, flush: 'post' }
  )
  watch(
    [() => data.value?.reaction === 'stopped', () => data.value?.reactionId],
    ([active, id], _previous, onCleanup) => {
      if (!active || id === undefined) return
      const timer = setTimeout(
        () => window.desktopMascotAPI?.reactionEnded(id),
        STATIC_REACTION_DURATION
      )
      onCleanup(() => clearTimeout(timer))
    },
    { immediate: true, flush: 'post' }
  )
  watch(
    [clip, motionDisabled, hidden],
    ([current, disabled, isHidden], _previous, onCleanup) => {
      let request = 0
      let timer: ReturnType<typeof setTimeout> | undefined
      onCleanup(() => {
        cancelAnimationFrame(request)
        clearTimeout(timer)
      })
      const finish = () => {
        if (current?.reactionId !== undefined)
          window.desktopMascotAPI?.reactionEnded(current.reactionId)
      }
      if (!current) return
      if (current.mode === 'stopped') return
      if (current.reactionId !== undefined && disabled) {
        timer = setTimeout(finish, STATIC_REACTION_DURATION)
        return
      }
      if (disabled || isHidden || current.mode === 'look') return
      let last = performance.now()
      const step = (now: number) => {
        progress += ((now - last) * current.fps) / 1000
        last = now
        if (current.mode === 'reaction' && progress >= current.count) {
          frame.value = current.count - 1
          finish()
          return
        }
        frame.value = Math.floor(progress) % current.count
        request = requestAnimationFrame(step)
      }
      request = requestAnimationFrame(step)
    },
    { immediate: true, flush: 'post' }
  )

  const sprite = computed(() => {
    const current = clip.value
    if (!current) return null
    const index =
      current.mode === 'look'
        ? current.look!
        : current.mode === 'stopped'
          ? Math.min(2, current.count - 1)
          : frame.value
    const column = index % current.columns
    const row =
      current.action * Math.ceil(current.count / current.columns) +
      Math.floor(index / current.columns)
    return {
      imageUrl: current.url,
      style: {
        width: `${current.columns * 100}%`,
        height: `${current.rows * 100}%`,
        transform: `translate(${(-column / current.columns) * 100}%, ${(-row / current.rows) * 100}%)`,
      },
    }
  })
  const updateVisibility = () => {
    hidden.value = document.hidden
  }
  document.addEventListener('visibilitychange', updateVisibility)
  onScopeDispose(() => {
    disposed = true
    decoded.clear()
    document.removeEventListener('visibilitychange', updateVisibility)
  })
  return { sprite, stopped }
}
