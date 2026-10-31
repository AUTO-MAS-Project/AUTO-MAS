<script setup lang="ts">
import { Empty, type EmptyProps } from 'ant-design-vue'
import noDataImage from '@/assets/NoData.svg'

defineProps<{
  description?: EmptyProps['description']
  imageStyle?: EmptyProps['imageStyle']
}>()
</script>

<template>
  <Empty
    :image="noDataImage"
    :description="description"
    :image-style="{ height: '80px', maxWidth: '100%', ...imageStyle }"
  >
    <template v-if="$slots.description" #description><slot name="description" /></template>
    <template v-if="$slots.default" #default><slot /></template>
  </Empty>
</template>
