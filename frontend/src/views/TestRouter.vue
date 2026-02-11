<template>
  <div class="test-container">
    <h2>测试路由页面</h2>

    <div class="test-section">
      <h3>应用对话框</h3>
      <p>点击按钮触发不同类型的对话框</p>

      <div class="button-group">
        <Button type="primary" @click="testBasicDialog">基本确认</Button>
        <Button type="primary" @click="testCustomDialog">自定义选项</Button>
        <Button type="primary" @click="testLongMessage">长信息对话框</Button>
      </div>

      <div v-if="lastResult !== null" class="result">
        <h4>上次选择结果</h4>
        <p :class="lastResult ? 'success' : 'cancel'">
          {{ lastResult ? '确认' : '取消' }}
        </p>
      </div>
    </div>

    <!-- 应用对话框 -->
    <Modal v-model:open="isModalOpen" :title="modalTitle" :closable="false" :maskClosable="false" :keyboard="true"
      centered>
      <p class="modal-message">{{ modalMessage }}</p>
      <template #footer>
        <Button v-for="(option, index) in modalOptions" :key="index" :type="index === 0 ? 'primary' : 'default'"
          @click="handleChoice(index === 0)">
          {{ option }}
        </Button>
      </template>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Modal, Button } from 'ant-design-vue'


defineOptions({
  name: 'TestRouterView',
})

const logger = window.electronAPI.getLogger('测试路由')
const lastResult = ref<boolean | null>(null)

// Modal ״̬
const isModalOpen = ref(false)
const modalTitle = ref('')
const modalMessage = ref('')
const modalOptions = ref<string[]>([])
let resolvePromise: ((value: boolean) => void) | null = null

// ��ʾ���������� Promise
const showModal = (options: {
  title: string
  message: string
  buttonOptions?: string[]
}): Promise<boolean> => {
  return new Promise(resolve => {
    modalTitle.value = options.title
    modalMessage.value = options.message
    modalOptions.value = options.buttonOptions || ['ȷ��', 'ȡ��']
    resolvePromise = resolve
    isModalOpen.value = true
  })
}

// �����û�ѡ��
const handleChoice = (choice: boolean) => {
  isModalOpen.value = false
  if (resolvePromise) {
    resolvePromise(choice)
    resolvePromise = null
  }
}

const testBasicDialog = async () => {
  try {
    const result = await showModal({
      title: '基本确认',
      message: '这是一个基本的确认对话框',
      buttonOptions: ['确认', '取消'],
    })
    lastResult.value = result
    logger.info(`基本确认对话框结果: ${result}`)
  } catch (error) {
    logger.error(`显示基本确认对话框失败: ${error}`)
  }
}

const testCustomDialog = async () => {
  try {
    const result = await showModal({
      title: '自定义选项',
      message: '是否要使用自定义模板',
      buttonOptions: ['使用', '取消'],
    })
    lastResult.value = result
    logger.info(`自定义选项对话框结果: ${result}`)
  } catch (error) {
    logger.error(`显示自定义选项对话框失败: ${error}`)
  }
}

const testLongMessage = async () => {
  try {
    const result = await showModal({
      title: '长信息对话框',
      message: `这是一个长信息对话框，用于测试显示长文本内容的效果。

这是一个长信息对话框，用于测试显示长文本内容的效果。

信息内容可以包含多行文本
并且可以显示详细的说明信息

是否要继续执行此操作`,
      buttonOptions: ['继续', '取消'],
    })
    lastResult.value = result
    logger.info(`长信息对话框结果: ${result}`)
  } catch (error) {
    logger.error(`显示长信息对话框失败: ${error}`)
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

.modal-message {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary, #595959);
  margin: 0;
  word-wrap: break-word;
  white-space: pre-wrap;
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

/* ��ɫģʽ֧�� */
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
