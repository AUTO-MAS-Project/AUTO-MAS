<template>
  <RuntimeBackendStartPanel v-bind="$attrs" />
</template>

<script setup lang="ts">
import RuntimeBackendStartPanel from './RuntimeBackendStartPanel.vue'

defineOptions({
  name: 'BackendStartStep',
  inheritAttrs: false,
})
</script>
