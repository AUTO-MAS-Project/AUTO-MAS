<!-- 特调插入点：按当前 flavor 在注册表里声明的组件依次渲染，没有就什么都不渲染。
     不包外层元素，渲染结果和直接写在页面里一样。组件以 context 一个 prop 接收上下文，
     save 事件原样交回页面。 -->
<template>
  <component
    :is="entry.component"
    v-for="(entry, index) in entries"
    :key="`${flavor.type}:${index}`"
    :context="context"
    @save="(key: string, value: unknown) => emit('save', key, value)"
  />
</template>

<script setup lang="ts" generic="N extends MaaFWFlavorSlotName">
import { computed } from 'vue'
import { resolveMaaFWFlavorSlot } from '@/composables/useMaaFWFlavor'
import type {
  MaaFWFlavor,
  MaaFWFlavorSlotContextMap,
  MaaFWFlavorSlotName,
} from '@/composables/maafwFlavorTypes'

const props = defineProps<{
  name: N
  flavor: MaaFWFlavor
  context: MaaFWFlavorSlotContextMap[N]
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

const entries = computed(() => resolveMaaFWFlavorSlot(props.flavor, props.name))
</script>
