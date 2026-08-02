<template>
  <Teleport to="body">
    <div v-if="visible" class="backend-startup-overlay">
      <div class="startup-content">
        <div class="windows-spinner" aria-label="加载中">
          <span v-for="index in 6" :key="index"></span>
        </div>
        <div class="startup-text">加载中</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
}>()
</script>

<style scoped>
.backend-startup-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  z-index: 9998;
}

.startup-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  text-align: center;
}

.windows-spinner {
  position: relative;
  width: 48px;
  height: 48px;
}

.windows-spinner span {
  position: absolute;
  top: 21px;
  left: 21px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #0078d4;
  animation: windows-spin 1.35s cubic-bezier(0.5, 0, 0.5, 1) infinite;
}

.windows-spinner span:nth-child(1) {
  animation-delay: -0.45s;
}

.windows-spinner span:nth-child(2) {
  animation-delay: -0.375s;
}

.windows-spinner span:nth-child(3) {
  animation-delay: -0.3s;
}

.windows-spinner span:nth-child(4) {
  animation-delay: -0.225s;
}

.windows-spinner span:nth-child(5) {
  animation-delay: -0.15s;
}

.windows-spinner span:nth-child(6) {
  animation-delay: -0.075s;
}

.startup-text {
  color: #202020;
  font-size: 15px;
  font-weight: 400;
}

@keyframes windows-spin {
  0% {
    transform: rotate(0deg) translateY(-18px);
    opacity: 0.3;
  }

  50% {
    opacity: 1;
  }

  100% {
    transform: rotate(360deg) translateY(-18px);
    opacity: 0.3;
  }
}
</style>
