<script setup lang="ts">
const props = defineProps<{
  goToLogs: () => void
  openDevTools: () => void
}>()

const { goToLogs, openDevTools } = props
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>开发者选项</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space size="large">
            <a-button type="primary" size="large" @click="goToLogs"> 查看日志 </a-button>
            <a-button size="large" @click="openDevTools"> 打开开发者工具 </a-button>
          </a-space>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
