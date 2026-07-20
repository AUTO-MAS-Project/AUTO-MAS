<script setup lang="ts">
import { Motion } from 'motion-v'
import { computed, useSlots } from 'vue'
import {
  getBlurRevealAnimate,
  getBlurRevealContent,
  getBlurRevealInitial,
  getBlurRevealTransition,
} from './blurRevealMotion'

interface Props {
  text?: string
  duration?: number
  delay?: number
  blur?: string
  yOffset?: number
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  text: '',
  duration: 1,
  delay: 1,
  blur: '10px',
  yOffset: 20,
  class: '',
})

const slots = useSlots()
const children = computed(() => getBlurRevealContent(props.text, slots.default?.() ?? []))

const getInitial = () => getBlurRevealInitial(props.blur, props.yOffset)
</script>

<template>
  <div :class="props.class">
    <Motion
      v-for="(child, index) in children"
      :key="index"
      as="div"
      :initial="getInitial()"
      :while-in-view="getBlurRevealAnimate()"
      :transition="getBlurRevealTransition(props.duration, props.delay, index)"
    >
      <template v-if="typeof child === 'string'">{{ child }}</template>
      <component :is="child" v-else />
    </Motion>
  </div>
</template>
