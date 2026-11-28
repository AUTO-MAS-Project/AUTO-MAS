<script setup lang="ts">
defineProps<{ name: string; logoSrc: string }>()
defineEmits<{ iconError: [event: Event] }>()
</script>

<template>
  <span v-if="name" class="account-identity" :title="name">
    <img :src="logoSrc" alt="" @error="$emit('iconError', $event)" />
    <span>{{ name }}</span>
  </span>
</template>

<style scoped>
.account-identity {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-weight: 600;
}

.account-identity img {
  width: 24px;
  height: 24px;
  object-fit: contain;
  flex: none;
}

.account-identity span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
