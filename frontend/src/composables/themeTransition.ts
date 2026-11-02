import { nextTick } from 'vue'

export type ThemeTransitionOptions = {
  origin: { x: number; y: number }
  disabled: boolean
}

const TRANSITION_CLASS = 'app-theme-transition'
const TRANSITION_DURATION = 800
let activeTransition: ViewTransition | undefined
let activeAnimation: Animation | undefined
let activeSurface: { element: HTMLElement; previousName: string } | undefined

export const cancelThemeTransition = (): void => {
  activeAnimation?.cancel()
  activeAnimation = undefined
  activeTransition?.skipTransition()
  activeTransition = undefined
  if (activeSurface) {
    activeSurface.element.style.viewTransitionName = activeSurface.previousName
    activeSurface = undefined
  }
  document.documentElement.classList.remove(TRANSITION_CLASS)
}

// 只等待主题和 Ant token 渲染；持久化仍走原保存队列，不占用浏览器快照阶段。
export const runThemeTransition = async (
  change: () => void,
  options?: ThemeTransitionOptions
): Promise<void> => {
  cancelThemeTransition()
  if (
    !options ||
    options.disabled ||
    !document.startViewTransition ||
    document.visibilityState !== 'visible' ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ) {
    change()
    await nextTick()
    return
  }

  const root = document.documentElement
  // 标题栏不参与快照，窗口按钮在扩散期间仍可点击。
  const surface = document.querySelector<HTMLElement>('.app-theme-surface') ?? root
  const rect = surface.getBoundingClientRect()
  const x = Math.max(0, Math.min(options.origin.x - rect.left, rect.width))
  const y = Math.max(0, Math.min(options.origin.y - rect.top, rect.height))
  const radius = Math.ceil(Math.hypot(Math.max(x, rect.width - x), Math.max(y, rect.height - y)))
  root.classList.add(TRANSITION_CLASS)
  activeSurface = { element: surface, previousName: surface.style.viewTransitionName }
  surface.style.viewTransitionName = 'root'
  const transition = document.startViewTransition(async () => {
    change()
    await nextTick()
  })
  activeTransition = transition

  void transition.ready
    .then(() => {
      if (activeTransition !== transition) return
      activeAnimation = root.animate(
        {
          clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`],
        },
        {
          duration: TRANSITION_DURATION,
          easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
          fill: 'both',
          pseudoElement: '::view-transition-new(root)',
        }
      )
    })
    .catch(() => transition.skipTransition())

  const cleanup = () => {
    if (activeTransition !== transition) return
    cancelThemeTransition()
  }
  void transition.finished.then(cleanup, cleanup)
  await transition.updateCallbackDone
}
