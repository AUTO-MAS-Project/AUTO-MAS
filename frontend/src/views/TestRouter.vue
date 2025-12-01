<template>
  <div class="test-container">
    <h2>对话框测试页面</h2>

    <div class="test-section">
      <h3>测试 showQuestionDialog</h3>
      <p>点击下面的按钮测试不同类型的对话框</p>

      <div class="button-group">
        <button class="test-button" @click="testBasicDialog">基础对话框</button>

        <button class="test-button" @click="testCustomDialog">自定义选项</button>

        <button class="test-button" @click="testLongMessage">长消息测试</button>
      </div>

      <div v-if="lastResult !== null" class="result">
        <h4>上次选择结果：</h4>
        <p :class="lastResult ? 'success' : 'cancel'">
          {{ lastResult ? '✓ 确认' : '✗ 取消' }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { getLogger } from '@/utils/logger'

defineOptions({
  name: 'TestRouterView',
})

const logger = getLogger('测试路由')
const lastResult = ref<boolean | null>(null)

const testBasicDialog = async () => {
  try {
    const result = await window.electronAPI.showQuestionDialog({
      title: '基础确认',
      message: '这是一个基础的确认对话框',
      options: ['确定', '取消'],
    })
    lastResult.value = result
    logger.info('基础对话框结果:', result)
  } catch (error) {
    logger.error('显示对话框失败:', error)
  }
}

const testCustomDialog = async () => {
  try {
    const result = await window.electronAPI.showQuestionDialog({
      title: '自定义选项',
      message: '是否要保存更改？',
      options: ['保存', '不保存'],
    })
    lastResult.value = result
    logger.info('自定义对话框结果:', result)
  } catch (error) {
    logger.error('显示对话框失败:', error)
  }
}

const testLongMessage = async () => {
  try {
    const result = await window.electronAPI.showQuestionDialog({
      title: '长消息测试',
      message: `这是一个包含较长消息的对话框测试。

消息���以包含多行文本，
用于显示更详细的信息。

是否要继续执行此操作？`,
      options: ['继续', '取消'],
    })
    lastResult.value = result
    logger.info('长消息对话框结果:', result)
  } catch (error) {
    logger.error('显示对话框失败:', error)
  }
}
</script>

<style scoped>
.test-container {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}

h2 {
  color: #262626;
  margin-bottom: 24px;
}

.test-section {
  background: #ffffff;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

h3 {
  color: #595959;
  font-size: 16px;
  margin-bottom: 12px;
}

p {
  color: #8c8c8c;
  margin-bottom: 16px;
}

.button-group {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.test-button {
  padding: 8px 16px;
  background: #1677ff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.test-button:hover {
  background: #4096ff;
}

.test-button:active {
  background: #0958d9;
}

.result {
  margin-top: 24px;
  padding: 16px;
  background: #f5f5f5;
  border-radius: 6px;
}

.result h4 {
  margin: 0 0 8px 0;
  color: #262626;
  font-size: 14px;
}

.result p {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.result p.success {
  color: #52c41a;
}

.result p.cancel {
  color: #ff4d4f;
}

/* 暗色模式支持 */
@media (prefers-color-scheme: dark) {
  h2 {
    color: #ffffff;
  }

  .test-section {
    background: #1f1f1f;
    border-color: #434343;
  }

  h3 {
    color: #c9cdd4;
  }

  p {
    color: #a6adb4;
  }

  .result {
    background: #2a2a2a;
  }

  .result h4 {
    color: #ffffff;
  }
}
</style>
