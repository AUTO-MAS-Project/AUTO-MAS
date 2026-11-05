import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
  type Ref,
} from 'vue'

export type SettingsLayoutMode = 'single' | 'dual'

interface SettingsSection {
  id: string
  title: string
  heading: HTMLElement
  card: HTMLElement
}

interface ReadingAnchor {
  card: HTMLElement
  offset: number
}

const SECTION_OFFSET = 24
const WIDE_LAYOUT_MIN_WIDTH = 1180

/** 同一组卡片的响应式排布、阅读位置与目录；不移动或重建子组件。 */
export function useSettingsSectionLayout(activeKey: Ref<string>, mode: Ref<SettingsLayoutMode>) {
  const layout = ref<HTMLElement | null>(null)
  const shell = ref<HTMLElement | null>(null)
  const sections = shallowRef<SettingsSection[]>([])
  const activeSection = ref('')
  const navigationTop = ref(0)
  const wide = ref(false)
  const isAbout = computed(() => activeKey.value === 'others')
  const effectiveDual = computed(() => !isAbout.value && mode.value === 'dual' && wide.value)
  const hasNavigation = computed(
    () => !isAbout.value && mode.value === 'single' && wide.value && sections.value.length > 1
  )

  let scroller: HTMLElement | null = null
  let content: HTMLElement | null = null
  let mutationObserver: MutationObserver | null = null
  let resizeObserver: ResizeObserver | null = null
  let layoutFrame: number | null = null
  let scrollFrame: number | null = null
  let anchor: ReadingAnchor | null = null
  let clickedSection: { id: string; top: number; settled: boolean } | null = null
  let sectionSequence = 0
  let disposed = false

  watch([mode, wide], () => {
    anchor ??= captureAnchor()
    clickedSection = null
    void nextTick().then(scheduleLayout)
  })

  watch(
    activeKey,
    async () => {
      anchor = null
      clickedSection = null
      await nextTick()
      if (disposed || !scroller) return
      scroller.scrollTop = 0
      observeActivePane()
    },
    { flush: 'post' }
  )

  onMounted(() => {
    scroller = layout.value?.querySelector<HTMLElement>('.ant-tabs-content-holder') ?? null
    scroller?.addEventListener('scroll', scheduleScrollSync, { passive: true })
    scroller?.addEventListener('wheel', clearClickedSection, { passive: true })
    scroller?.addEventListener('touchstart', clearClickedSection, { passive: true })
    scroller?.addEventListener('pointerdown', clearClickedSection, { passive: true })
    scroller?.addEventListener('keydown', clearClickedSection)
    mutationObserver = new MutationObserver(collectSections)
    resizeObserver = new ResizeObserver(() => {
      wide.value = (layout.value?.clientWidth ?? 0) >= WIDE_LAYOUT_MIN_WIDTH
      scheduleLayout()
    })
    observeActivePane()
  })

  onBeforeUnmount(() => {
    disposed = true
    scroller?.removeEventListener('scroll', scheduleScrollSync)
    scroller?.removeEventListener('wheel', clearClickedSection)
    scroller?.removeEventListener('touchstart', clearClickedSection)
    scroller?.removeEventListener('pointerdown', clearClickedSection)
    scroller?.removeEventListener('keydown', clearClickedSection)
    mutationObserver?.disconnect()
    resizeObserver?.disconnect()
    if (layoutFrame !== null) cancelAnimationFrame(layoutFrame)
    if (scrollFrame !== null) cancelAnimationFrame(scrollFrame)
  })

  function observeActivePane() {
    mutationObserver?.disconnect()
    resizeObserver?.disconnect()
    const pane = layout.value?.querySelector<HTMLElement>('.ant-tabs-tabpane-active')
    content = pane?.querySelector<HTMLElement>('.tab-content') ?? null
    if (!pane || !scroller || !layout.value) return
    mutationObserver?.observe(pane, { childList: true, characterData: true, subtree: true })
    resizeObserver?.observe(layout.value)
    resizeObserver?.observe(scroller)
    resizeObserver?.observe(pane)
    collectSections()
  }

  function collectSections() {
    const headings = isAbout.value
      ? []
      : content?.querySelectorAll<HTMLElement>(':scope > .form-section > .section-header > h3')
    sections.value = Array.from(headings ?? []).flatMap(heading => {
      const title = heading.textContent?.replace(/\s+/g, ' ').trim()
      const card = heading.closest<HTMLElement>('.form-section')
      if (!title || !card) return []
      // 异步插入新卡片时不复用索引，避免与已有标题的锚点冲突。
      heading.id ||= `settings-${activeKey.value}-section-${sectionSequence++}`
      heading.tabIndex = -1
      resizeObserver?.observe(card)
      return [{ id: heading.id, title, heading, card }]
    })
    scheduleLayout()
  }

  function scheduleLayout() {
    if (disposed || layoutFrame !== null) return
    layoutFrame = requestAnimationFrame(() => {
      layoutFrame = null
      arrangeCards()
      if (anchor?.card.isConnected && scroller) {
        scroller.scrollTop +=
          anchor.card.getBoundingClientRect().top -
          scroller.getBoundingClientRect().top -
          anchor.offset
      }
      anchor = null
      syncPosition()
    })
  }

  function arrangeCards() {
    if (!content) return
    content.classList.toggle('settings-card-grid', effectiveDual.value)
    const children = Array.from(content.children).filter(
      (child): child is HTMLElement => child instanceof HTMLElement
    )
    if (!effectiveDual.value) {
      for (const child of children) {
        child.style.removeProperty('grid-column')
        child.style.removeProperty('grid-row')
      }
      return
    }

    // 先设置列宽再测高度。行以 1px 计，左右各自累积；DOM 仍是原始顺序。
    const visibleChildren = children.filter(child => {
      const style = getComputedStyle(child)
      return style.display !== 'none' && style.position !== 'absolute' && style.position !== 'fixed'
    })
    let cardIndex = 0
    for (const child of visibleChildren) {
      child.style.gridColumn = child.matches('.form-section')
        ? `${(cardIndex++ % 2) + 1}`
        : '1 / -1'
    }
    const bottoms = [0, 0]
    cardIndex = 0
    for (const child of visibleChildren) {
      const style = getComputedStyle(child)
      const height = Math.max(
        1,
        Math.ceil(
          child.getBoundingClientRect().height +
            parseFloat(style.marginTop) +
            parseFloat(style.marginBottom)
        )
      )
      if (child.matches('.form-section')) {
        const column = cardIndex++ % 2
        child.style.gridRow = `${bottoms[column] + 1} / span ${height}`
        bottoms[column] += height
      } else {
        const top = Math.max(...bottoms)
        child.style.gridRow = `${top + 1} / span ${height}`
        bottoms.fill(top + height)
      }
    }
  }

  function captureAnchor(): ReadingAnchor | null {
    if (!scroller) return null
    const top = scroller.getBoundingClientRect().top
    const visible = sections.value.filter(
      section => section.card.getBoundingClientRect().bottom > top
    )
    const current = visible.reduce<SettingsSection | undefined>((nearest, section) => {
      const distance = Math.abs(section.card.getBoundingClientRect().top - top - SECTION_OFFSET)
      return !nearest ||
        distance < Math.abs(nearest.card.getBoundingClientRect().top - top - SECTION_OFFSET)
        ? section
        : nearest
    }, undefined)
    return current
      ? { card: current.card, offset: current.card.getBoundingClientRect().top - top }
      : null
  }

  function scheduleScrollSync() {
    if (scrollFrame !== null) return
    scrollFrame = requestAnimationFrame(() => {
      scrollFrame = null
      syncPosition()
    })
  }

  function syncPosition() {
    if (!scroller || !shell.value || !sections.value.length) return
    const top = scroller.getBoundingClientRect().top
    navigationTop.value = top - shell.value.getBoundingClientRect().top + SECTION_OFFSET
    if (clickedSection) {
      const reachedTarget = Math.abs(scroller.scrollTop - clickedSection.top) <= 1
      if (!clickedSection.settled || reachedTarget) {
        clickedSection.settled ||= reachedTarget
        activeSection.value = clickedSection.id
        return
      }
      clickedSection = null
    }
    let current = sections.value[0]
    for (const section of sections.value) {
      if (section.heading.getBoundingClientRect().top <= top + SECTION_OFFSET + 1) current = section
    }
    // 页尾短卡片无法滚到顶部时，仍能激活最后一个目录项。
    if (
      scroller.scrollHeight > scroller.clientHeight + 1 &&
      scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1
    )
      current = sections.value[sections.value.length - 1]
    activeSection.value = current.id
  }

  function clearClickedSection() {
    clickedSection = null
    scheduleScrollSync()
  }

  function scrollToSection(section: SettingsSection) {
    if (!scroller) return
    const top =
      scroller.scrollTop +
      section.heading.getBoundingClientRect().top -
      scroller.getBoundingClientRect().top -
      SECTION_OFFSET
    clickedSection = {
      id: section.id,
      top: Math.max(0, Math.min(top, scroller.scrollHeight - scroller.clientHeight)),
      settled: false,
    }
    activeSection.value = section.id
    section.heading.focus({ preventScroll: true })
    scroller.scrollTo({
      top,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    })
  }

  return {
    layout,
    shell,
    sections,
    activeSection,
    navigationTop,
    effectiveDual,
    hasNavigation,
    scrollToSection,
  }
}
