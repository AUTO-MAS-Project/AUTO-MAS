<!-- 特调插入点：按当前 flavor 在注册表里为这一页这个位置声明的组件依次渲染，没有就什么都不渲染。
     不包外层元素，渲染结果和直接写在页面里一样。组件以 context 一个 prop 接收上下文；
     只转发这一部分的事件（脚本页 change、用户页 save；新建流程只读，什么都不转发），
     别的事件不挂到组件上。 -->
<template>
  <component
    :is="entry.component"
    v-for="(entry, index) in entries"
    :key="`${flavor.type}:${index}`"
    :context="context"
    v-on="listeners"
  />
</template>

<script setup lang="ts" generic="P extends MaaFWFlavorPart, N extends MaaFWFlavorSlotName<P>">
import { computed } from 'vue'
import { resolveMaaFWFlavorSlot } from '@/composables/useMaaFWFlavor'
import type {
  MaaFWFlavor,
  MaaFWFlavorPart,
  MaaFWFlavorSlotContextMap,
  MaaFWFlavorSlotEmitMap,
  MaaFWFlavorSlotName,
} from '@/composables/maafwFlavorTypes'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  part: P
  name: N
  flavor: MaaFWFlavor
  context: MaaFWFlavorSlotContextMap[P][N]
  /** 只渲染这个插入点的第几个组件（外层要给每个组件单独排版时用）；不传渲染全部 */
  index?: number
}>()

const emit = defineEmits<{
  change: MaaFWFlavorSlotEmitMap['scriptPage']['change']
  save: MaaFWFlavorSlotEmitMap['userPage']['save']
}>()

const entries = computed(() => {
  const all = resolveMaaFWFlavorSlot(props.flavor, props.part, props.name)
  return props.index === undefined ? all : all.slice(props.index, props.index + 1)
})

const listeners = computed(() => {
  switch (props.part) {
    case 'scriptPage':
      return {
        change: (...args: MaaFWFlavorSlotEmitMap['scriptPage']['change']) =>
          emit('change', ...args),
      }
    case 'userPage':
      return {
        save: (...args: MaaFWFlavorSlotEmitMap['userPage']['save']) => emit('save', ...args),
      }
    default:
      // 新建流程的插入点只读
      return {}
  }
})
</script>
