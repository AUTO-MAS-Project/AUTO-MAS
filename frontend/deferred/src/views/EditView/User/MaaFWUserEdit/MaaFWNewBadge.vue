<template>
  <span v-if="dot" class="maafw-new-dot" aria-hidden="true"></span>
  <span v-else class="maafw-new-badge">✦ NEW</span>
</template>

<script setup lang="ts">
// 「添加任务」里新出现的任务：任务项与输入框上是 NEW 标签，分组上是一个点
defineProps<{ dot?: boolean }>()
</script>

<style scoped>
.maafw-new-badge {
  display: inline-flex;
  align-items: center;
  flex: none;
  padding: 0 6px;
  border-radius: 10px;
  background: linear-gradient(90deg, #ff4d8c, #ffa940);
  box-shadow: 0 0 6px rgb(255 89 128 / 45%);
  color: #fff;
  font-size: 10px;
  font-weight: 900;
  line-height: 16px;
  letter-spacing: 0.2px;
  white-space: nowrap;
}

.maafw-new-dot {
  display: inline-block;
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-error);
}
</style>
