<script setup lang="ts">
import { computed } from 'vue'
import { Empty, type EmptyProps } from 'ant-design-vue'
import noDataImage from '@/assets/NoData.svg'

export type NoDataSize = 'sm' | 'md' | 'lg'

const SIZE_HEIGHT_MAP: Record<NoDataSize, string> = {
  sm: '64px',
  md: '80px',
  lg: '120px',
}

const props = withDefaults(
  defineProps<{
    title?: string
    description?: EmptyProps['description']
    size?: NoDataSize
    imageStyle?: EmptyProps['imageStyle']
  }>(),
  {
    title: undefined,
    description: undefined,
    size: 'md',
    imageStyle: undefined,
  }
)

const resolvedImageStyle = computed(() => ({
  height: SIZE_HEIGHT_MAP[props.size],
  maxWidth: '100%',
  ...props.imageStyle,
}))
</script>

<template>
  <Empty
    :image="noDataImage"
    :description="title ? undefined : description"
    :image-style="resolvedImageStyle"
  >
    <template v-if="$slots.description || title" #description>
      <slot name="description">
        <div class="no-data-title">{{ title }}</div>
        <div v-if="description" class="no-data-description">{{ description }}</div>
      </slot>
    </template>
    <template v-if="$slots.default" #default><slot /></template>
  </Empty>
</template>

<style scoped>
.no-data-title {
  color: var(--ant-color-text);
  font-size: 15px;
  font-weight: 500;
  line-height: 22px;
}

.no-data-description {
  margin-top: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 20px;
}
</style>
