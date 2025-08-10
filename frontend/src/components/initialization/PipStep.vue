<template>
  <div class="step-panel">
    <h3>安装 pip 包管理器</h3>
    <div v-if="!pipInstalled" class="install-section">
      <p>pip 是 Python 的包管理工具，用于安装和管理 Python 包</p>
      
      <div class="pip-info">
        <a-alert 
          message="pip 安装信息" 
          description="将自动下载并安装 pip 包管理器，这是安装 Python 依赖包的必要工具。"
          type="info" 
          show-icon 
        />
      </div>
    </div>
    <div v-else class="already-installed">
      <a-result status="success" title="pip已成功安装，无需继续安装" />
      <div class="reinstall-section">
        <a-button type="primary" danger @click="handleForceReinstall" :loading="reinstalling">
          {{ reinstalling ? '正在重新安装...' : '强制重新安装' }}
        </a-button>
        <p class="reinstall-note">点击此按钮将删除现有pip环境并重新安装</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  pipInstalled: boolean
}>()

const reinstalling = ref(false)

// 强制重新安装pip
async function handleForceReinstall() {
  reinstalling.value = true
  try {
    console.log('开始强制重新安装pip')
    // 先删除现有pip
    const deleteResult = await window.electronAPI.deletePip()
    if (!deleteResult.success) {
      throw new Error(`删除pip失败: ${deleteResult.error}`)
    }
    
    // 重新安装pip
    const installResult = await window.electronAPI.installPip()
    if (!installResult.success) {
      throw new Error(`重新安装pip失败: ${installResult.error}`)
    }
    
    console.log('pip强制重新安装成功')
    // 通知父组件更新状态
    window.location.reload() // 简单的页面刷新来更新状态
  } catch (error) {
    console.error('pip强制重新安装失败:', error)
    // 这里可以添加错误提示
  } finally {
    reinstalling.value = false
  }
}

defineExpose({
  handleForceReinstall
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

.pip-info {
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

.reinstall-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.reinstall-note {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  text-align: center;
  margin: 0;
}
</style>