<template>
  <Transition name="back-to-top">
    <div v-if="visible" class="back-to-top" @click="scrollToTop">
      <UpOutlined class="back-to-top-icon" />
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { UpOutlined } from '@ant-design/icons-vue'

defineOptions({ name: 'HomeBackToTop' })

const visible = ref(false)
const THRESHOLD = 300
let scrollContainer: Element | null = null

const checkScroll = () => {
  if (!scrollContainer) return
  visible.value = scrollContainer.scrollTop > THRESHOLD
}

const scrollToTop = () => {
  scrollContainer?.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => {
  scrollContainer = document.querySelector('.content-area')
  if (!scrollContainer) return
  scrollContainer.addEventListener('scroll', checkScroll, { passive: true })
  checkScroll()
})

onBeforeUnmount(() => {
  scrollContainer?.removeEventListener('scroll', checkScroll)
})
</script>

<style scoped>
.back-to-top {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 100;
  width: 50px;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--ant-color-primary);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: background 0.2s, transform 0.2s;
}

.back-to-top:hover {
  background: var(--ant-color-primary-hover);
  transform: translateY(-2px);
}

.back-to-top-icon {
  font-size: 16px;
}

.back-to-top-enter-active,
.back-to-top-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.back-to-top-enter-from,
.back-to-top-leave-to {
  opacity: 0;
  transform: scale(0.8);
}
</style>
