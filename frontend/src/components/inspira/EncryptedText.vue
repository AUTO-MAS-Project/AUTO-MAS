<script setup lang="ts">
import { Motion, useInView } from 'motion-v'
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  calculateRevealCount,
  generateGibberishPreservingSpaces,
  getDisplayCharacter,
} from './encryptedTextMotion'

interface Props {
  text: string
  class?: string
  revealDelayMs?: number
  charset?: string
  flipDelayMs?: number
  encryptedClass?: string
  revealedClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  class: '',
  revealDelayMs: 50,
  charset:
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-={}[];:,.<>/?',
  flipDelayMs: 50,
  encryptedClass: '',
  revealedClass: '',
})

const containerRef = ref<HTMLElement>()
const isInView = useInView(containerRef)
const revealCount = ref(0)
const animationFrameId = ref<number | null>(null)
const startTime = ref(0)
const lastFlipTime = ref(0)
const scrambledCharacters = ref<string[]>([])

const textCharacters = computed(() => Array.from(props.text))

const stopAnimation = () => {
  if (animationFrameId.value === null) return
  cancelAnimationFrame(animationFrameId.value)
  animationFrameId.value = null
}

const resetAnimation = () => {
  scrambledCharacters.value = Array.from(
    generateGibberishPreservingSpaces(props.text, props.charset)
  )
  startTime.value = performance.now()
  lastFlipTime.value = startTime.value
  revealCount.value = 0
}

const updateAnimation = (now: number) => {
  revealCount.value = calculateRevealCount(
    now - startTime.value,
    props.revealDelayMs,
    textCharacters.value.length
  )

  if (revealCount.value >= textCharacters.value.length) {
    animationFrameId.value = null
    return
  }

  if (now - lastFlipTime.value >= Math.max(0, props.flipDelayMs)) {
    scrambledCharacters.value = Array.from(
      generateGibberishPreservingSpaces(props.text, props.charset),
      (character, index) =>
        index < revealCount.value ? (textCharacters.value[index] ?? '') : character
    )
    lastFlipTime.value = now
  }

  animationFrameId.value = requestAnimationFrame(updateAnimation)
}

const startAnimation = () => {
  stopAnimation()
  if (!props.text) return
  resetAnimation()
  animationFrameId.value = requestAnimationFrame(updateAnimation)
}

const getCharacterClass = (index: number) =>
  index < revealCount.value ? props.revealedClass : props.encryptedClass

watch(isInView, visible => {
  if (visible) {
    startAnimation()
  } else {
    stopAnimation()
    revealCount.value = 0
  }
})

watch(
  () => props.text,
  () => {
    resetAnimation()
    if (isInView.value) startAnimation()
  },
  { immediate: true }
)

onUnmounted(stopAnimation)
</script>

<template>
  <Motion ref="containerRef" as="span" :class="props.class" :aria-label="text" role="text">
    <span
      v-for="(_character, index) in textCharacters"
      :key="index"
      :class="getCharacterClass(index)"
      aria-hidden="true"
    >
      {{ getDisplayCharacter(props.text, scrambledCharacters, index, revealCount) }}
    </span>
  </Motion>
</template>
