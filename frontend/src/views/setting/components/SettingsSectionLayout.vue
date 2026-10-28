<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

interface SettingsSection {
  id: string
  title: string
  heading: HTMLElement
}

defineProps<{ loading: boolean }>()
const activeKey = defineModel<string>('activeKey', { required: true })

const { t } = useI18n()
const layout = ref<HTMLElement | null>(null)
const sections = shallowRef<SettingsSection[]>([])
const activeSection = ref('')
const navigationTop = ref(0)
const tabs = computed(() => [
  { key: 'basic', title: t('core.setting.tab.basic') },
  { key: 'function', title: t('core.setting.tab.function') },
  { key: 'notify', title: t('core.setting.tab.notify') },
  { key: 'advanced', title: t('core.setting.tab.advanced') },
  { key: 'others', title: t('core.setting.tab.others') },
])

const SECTION_OFFSET = 24
let scroller: HTMLElement | null = null
let mutationObserver: MutationObserver | null = null
let resizeObserver: ResizeObserver | null = null
let scrollFrame: number | null = null

watch(
  activeKey,
  async () => {
    await nextTick()
    if (!scroller || !layout.value) return
    scroller.scrollTop = 0
    observeActivePane()
  },
  { flush: 'post' }
)

onMounted(() => {
  scroller = layout.value?.querySelector<HTMLElement>('.ant-tabs-content-holder') ?? null
  scroller?.addEventListener('scroll', scheduleScrollSync, { passive: true })
  mutationObserver = new MutationObserver(collectSections)
  resizeObserver = new ResizeObserver(syncPosition)
  observeActivePane()
})

onBeforeUnmount(() => {
  scroller?.removeEventListener('scroll', scheduleScrollSync)
  mutationObserver?.disconnect()
  resizeObserver?.disconnect()
  if (scrollFrame !== null) cancelAnimationFrame(scrollFrame)
  scroller = null
})

function observeActivePane() {
  mutationObserver?.disconnect()
  resizeObserver?.disconnect()
  const pane = layout.value?.querySelector<HTMLElement>('.ant-tabs-tabpane-active')
  if (!pane || !scroller || !layout.value) return

  // 只观察当前分类，异步加载和切换语言后仍从真实标题生成目录。
  mutationObserver?.observe(pane, { childList: true, characterData: true, subtree: true })
  resizeObserver?.observe(layout.value)
  resizeObserver?.observe(scroller)
  resizeObserver?.observe(pane)
  collectSections()
}

function collectSections() {
  const pane = layout.value?.querySelector<HTMLElement>('.ant-tabs-tabpane-active')
  const headings = pane?.querySelectorAll<HTMLElement>(
    '.form-section > .section-header > h3, .notify-tab > .panel > .panel-head > h3'
  )
  sections.value = Array.from(headings ?? []).flatMap((heading, index) => {
    const title = heading.textContent?.replace(/\s+/g, ' ').trim()
    if (!title) return []
    heading.id ||= `settings-${activeKey.value}-section-${index}`
    return [{ id: heading.id, title, heading }]
  })
  syncPosition()
}

function scheduleScrollSync() {
  if (scrollFrame !== null) return
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = null
    syncPosition()
  })
}

function syncPosition() {
  if (!scroller || !layout.value || !sections.value.length) return
  const scrollTop = scroller.getBoundingClientRect().top
  navigationTop.value = scrollTop - layout.value.getBoundingClientRect().top + SECTION_OFFSET
  let current = sections.value[0]
  for (const section of sections.value) {
    if (section.heading.getBoundingClientRect().top <= scrollTop + SECTION_OFFSET + 1) {
      current = section
    }
  }

  // 页尾的短分区未必能滚到顶部，抵达底部时仍正确高亮最后一项。
  if (
    scroller.scrollHeight > scroller.clientHeight + 1 &&
    scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1
  ) {
    current = sections.value[sections.value.length - 1]
  }
  activeSection.value = current.id
}

function scrollToSection(section: SettingsSection) {
  if (!scroller) return
  const top =
    scroller.scrollTop +
    section.heading.getBoundingClientRect().top -
    scroller.getBoundingClientRect().top -
    SECTION_OFFSET
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  scroller.scrollTo({ top, behavior: reducedMotion ? 'auto' : 'smooth' })
  activeSection.value = section.id
}
</script>

<template>
  <div
    ref="layout"
    class="settings-content settings-section-layout"
    :class="{ 'settings-section-layout--with-nav': sections.length > 1 }"
    :aria-busy="loading"
  >
    <a-tabs v-model:active-key="activeKey" type="card" :animated="false" class="settings-tabs">
      <a-tab-pane v-for="tab in tabs" :key="tab.key" :tab="tab.title">
        <div class="settings-pane">
          <slot :name="tab.key" />
        </div>
      </a-tab-pane>
    </a-tabs>

    <nav
      v-if="sections.length > 1"
      class="settings-section-navigation"
      :aria-label="t('core.setting.navigation.ariaLabel')"
      :style="{ top: `${navigationTop}px` }"
    >
      <div class="navigation-title">{{ t('core.setting.navigation.title') }}</div>
      <ul class="navigation-list">
        <li v-for="section in sections" :key="section.id">
          <button
            type="button"
            class="navigation-link"
            :class="{ 'navigation-link--active': activeSection === section.id }"
            :aria-current="activeSection === section.id ? 'location' : undefined"
            :aria-controls="section.id"
            @click="scrollToSection(section)"
          >
            {{ section.title }}
          </button>
        </li>
      </ul>
    </nav>
  </div>
</template>

<style scoped>
.settings-section-layout {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-radius: 12px;
  background: var(--ant-color-bg-container);
}

.settings-tabs {
  flex: 1;
  min-height: 0;
  padding: 12px;
}

.settings-tabs :deep(.ant-tabs-nav) {
  flex: 0 0 auto;
  margin: 0;
}

.settings-tabs :deep(.ant-tabs-content-holder) {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: contain;
}

.settings-tabs :deep(.ant-tabs-tab) {
  margin-right: 8px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px 8px 0 0;
  background: transparent;
}

.settings-tabs :deep(.ant-tabs-tab-active) {
  border-bottom-color: var(--ant-color-bg-container);
  background: var(--ant-color-bg-container);
}

.settings-tabs :deep(.tab-content) {
  width: 100%;
  padding: 24px;
}

.settings-tabs :deep(.section-header) {
  border-bottom-width: 1px;
}

.settings-tabs :deep(.section-header h3::before) {
  display: none;
}

.settings-section-navigation {
  position: absolute;
  right: 24px;
  display: none;
  width: 160px;
}

.navigation-title {
  margin-bottom: 12px;
  padding-left: 16px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.navigation-list {
  margin: 0;
  padding: 0;
  border-left: 1px solid var(--ant-color-border-secondary);
  list-style: none;
}

.navigation-link {
  position: relative;
  display: block;
  width: 100%;
  padding: 8px 0 8px 16px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--ant-color-text-secondary);
  font: inherit;
  font-size: 13px;
  line-height: 20px;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
}

.navigation-link:hover,
.navigation-link--active {
  color: var(--ant-color-primary);
}

.navigation-link--active::before {
  position: absolute;
  top: 9px;
  bottom: 9px;
  left: -1px;
  width: 3px;
  border-radius: 2px;
  background: var(--ant-color-primary);
  content: '';
}

.navigation-link:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

@media (min-width: 1440px) and (min-height: 640px) {
  .settings-section-layout--with-nav .settings-pane {
    padding-right: 200px;
  }

  .settings-section-navigation {
    display: block;
  }
}
</style>
