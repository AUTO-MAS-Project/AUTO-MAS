<script setup lang="ts">
const { goToLogs, openDevTools } = defineProps<{ goToLogs: () => void; openDevTools: () => void }>()
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
            <a-button type="primary" @click="goToLogs" size="large"> 查看日志 </a-button>
            <a-button @click="openDevTools" size="large"> 打开开发者工具 </a-button>
          </a-space>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
