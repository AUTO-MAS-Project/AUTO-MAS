<script setup lang="ts">
import { onMounted } from 'vue'
import { ConfigProvider } from 'ant-design-vue'
import { useTheme } from './composables/useTheme.ts'
import AppLayout from './components/AppLayout.vue'

const { antdTheme, initTheme } = useTheme()

onMounted(() => {
  initTheme()
})
</script>

<template>
  <ConfigProvider :theme="antdTheme">
    <AppLayout />
  </ConfigProvider>
</template>

<style>
* {
  box-sizing: border-box;
}
</style>
