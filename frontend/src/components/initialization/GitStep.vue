<template>
  <div class="step-panel">
    <h3>Git 版本控制工具</h3>
    <div v-if="!gitInstalled" class="install-section">
      <p>需要安装 Git 工具来获取源代码</p>
      <div class="git-info">
        <a-alert
          message="Git 工具信息"
          description="将安装便携版 Git 工具，以实现后端代码更新。"
          type="info"
          show-icon
        />
      </div>
    </div>
    <div v-else class="already-installed">
      <a-result status="success" title="Git已成功安装，无需继续安装" />
      <!--      <div class="reinstall-section">-->
      <!--        <a-button type="primary" danger @click="handleForceReinstall" :loading="reinstalling">-->
      <!--          {{ reinstalling ? '正在重新安装...' : '强制重新安装' }}-->
      <!--        </a-button>-->
      <!--        <p class="reinstall-note">点击此按钮将删除现有Git环境并重新安装</p>-->
      <!--      </div>-->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  gitInstalled: boolean
}>()

const reinstalling = ref(false)

// 强制重新安装Git
async function handleForceReinstall() {
  reinstalling.value = true
  try {
    console.log('开始强制重新安装Git')
    // 先删除现有Git
    const deleteResult = await window.electronAPI.deleteGit()
    if (!deleteResult.success) {
      throw new Error(`删除Git失败: ${deleteResult.error}`)
    }

    // 重新安装Git
    const installResult = await window.electronAPI.downloadGit()
    if (!installResult.success) {
      throw new Error(`重新安装Git失败: ${installResult.error}`)
    }

    console.log('Git强制重新安装成功')
    // 通知父组件更新状态
    window.location.reload() // 简单的页面刷新来更新状态
  } catch (error) {
    console.error('Git强制重新安装失败:', error)
    // 这里可以添加错误提示
  } finally {
    reinstalling.value = false
  }
}

defineExpose({
  handleForceReinstall,
})
</script>

<style scoped>
.step-panel {
  padding: 20px;
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.step-panel h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
}

.install-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.install-section p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.git-info {
  margin-top: 16px;
}

.already-installed {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 200px;
  gap: 20px;
}

</style>