<template>
  <!-- 按脚本实际类型选的页面；还没读到脚本、或正在纠正地址时什么都不渲染 -->
  <component :is="page" v-if="page" />
</template>

<script setup lang="ts">
import { useMaaFWPageHost } from './useMaaFWPageHost'

// MaaFW 家族全部路由的组件：选页面、纠正后缀写错的地址、把上下文交给页面（见 useMaaFWPageHost）
defineOptions({ name: 'MaaFWPageHost' })

const { page } = useMaaFWPageHost()
</script>
