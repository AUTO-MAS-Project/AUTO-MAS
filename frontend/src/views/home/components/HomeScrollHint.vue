<template>
  <Transition name="scroll-hint">
    <button v-if="visible" class="scroll-hint" aria-label="向下滚动查看更多内容" @click="scrollDown">
      <span class="scroll-hint-text">下方还有更多内容</span>
      <DownOutlined class="scroll-hint-arrow" />
    </button>
  </Transition>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { DownOutlined } from '@ant-design/icons-vue'

defineOptions({ name: 'HomeScrollHint' })

const visible = ref(false)
const THRESHOLD = 200
let scrollContainer: Element | null = null
let observer: MutationObserver | null = null

const checkScroll = () => {
  if (!scrollContainer) return
  const el = scrollContainer
  const scrollable = el.scrollHeight > el.clientHeight + THRESHOLD
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - THRESHOLD
  visible.value = scrollable && !atBottom
}

const scrollDown = () => {
  scrollContainer?.scrollBy({ top: 400, behavior: 'smooth' })
}

onMounted(() => {
  scrollContainer = document.querySelector('.content-area')
  if (!scrollContainer) return
  scrollContainer.addEventListener('scroll', checkScroll, { passive: true })
  observer = new MutationObserver(checkScroll)
  observer.observe(scrollContainer, { childList: true, subtree: true })
  checkScroll()
})

onBeforeUnmount(() => {
  scrollContainer?.removeEventListener('scroll', checkScroll)
  observer?.disconnect()
})
</script>

<style scoped>
.scroll-hint {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px 24px 20px;
  border: none;
  cursor: pointer;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.2) 100%);
  border-radius: 12px 12px 0 0;
  transition: opacity 0.3s;
}

.scroll-hint:hover {
  opacity: 0.8;
}

.scroll-hint:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

.scroll-hint-text {
  color: var(--ant-color-primary);
  font-size: 12px;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.scroll-hint-arrow {
  color: var(--ant-color-primary);
  font-size: 16px;
  animation: bounce 1.5s ease-in-out infinite;
}

@keyframes bounce {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(5px);
  }
}

.scroll-hint-enter-active,
.scroll-hint-leave-active {
  transition:
    opacity 0.4s ease,
    transform 0.4s ease;
}

.scroll-hint-enter-from,
.scroll-hint-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(10px);
}
</style>
