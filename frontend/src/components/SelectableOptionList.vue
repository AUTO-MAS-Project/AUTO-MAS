<template>
  <a-radio-group v-model:value="value" class="selectable-option-list">
    <slot />
  </a-radio-group>
</template>

<script setup lang="ts" generic="T extends string | null">
const value = defineModel<T>({ required: true })
</script>

<style scoped>
.selectable-option-list {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 10px;
}
</style>
