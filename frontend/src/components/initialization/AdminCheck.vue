<template>
  <div class="admin-check">
    <a-result
      status="warning"
      title="需要管理员权限"
      sub-title="为了正常安装和配置环境，请以管理员权限运行此应用"
    >
      <template #extra>
        <a-button type="primary" @click="handleRestartAsAdmin"> 重新以管理员权限启动 </a-button>
      </template>
    </a-result>
  </div>
</template>

<script setup lang="ts">


async function handleRestartAsAdmin() {
  try {
    await window.electronAPI.restartAsAdmin()
  } catch (error) {
    console.error('重启为管理员失败', error)
  }
}
</script>

<style scoped>
.admin-check {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
}
</style>
