<template>
  <div class="log-timestamp-selector">
    <!-- 切换视图模式 -->
    <a-radio-group v-model:value="viewMode" style="margin-bottom: 16px" @change="onViewModeChange">
      <a-radio-button value="input">输入框模式</a-radio-button>
      <a-radio-button value="visual">可视化选择模式</a-radio-button>
    </a-radio-group>

    <!-- 输入框模式 -->
    <div v-if="viewMode === 'input'">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item name="logTimeStart" :rules="rules.logTimeStart">
            <template #label>
              <a-tooltip title="脚本日志时间戳起始位置">
                <span class="form-label">
                  日志时间戳起始位置
                  <QuestionCircleOutlined class="help-icon" />
                </span>
              </a-tooltip>
            </template>
            <a-input-number
              v-model:value="formData.logTimeStart"
              :min="1"
              :max="9999"
              size="large"
              class="modern-number-input"
              style="width: 100%"
              @blur="handleChange('Script', 'LogTimeStart', formData.logTimeStart)"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item name="logTimeEnd" :rules="rules.logTimeEnd">
            <template #label>
              <a-tooltip title="脚本日志时间戳结束位置">
                <span class="form-label">
                  日志时间戳结束位置
                  <QuestionCircleOutlined class="help-icon" />
                </span>
              </a-tooltip>
            </template>
            <a-input-number
              v-model:value="formData.logTimeEnd"
              :min="1"
              :max="9999"
              size="large"
              class="modern-number-input"
              style="width: 100%"
              @blur="handleChange('Script', 'LogTimeEnd', formData.logTimeEnd)"
            />
          </a-form-item>
        </a-col>
      </a-row>
    </div>

    <!-- 可视化选择模式 -->
    <div v-else-if="viewMode === 'visual'">
      <div class="visual-mode-container">
        <div class="log-preview-header">
          <span>日志预览 (使用鼠标文本选择功能选择时间戳区域)</span>
          <a-button
            type="primary"
            :loading="loadingPreview"
            :disabled="!logFilePath"
            @click="loadLogFile"
          >
            加载日志
          </a-button>
        </div>

        <div
          ref="logPreviewRef"
          class="log-preview-area"
          @mouseup="handleMouseUp"
          @mouseleave="handleMouseLeave"
        >
          <div
            v-for="(line, index) in logLines"
            :key="index"
            class="log-line"
            :data-line-index="index"
          >
            <span class="line-number">{{ index + 1 }}</span>
            <span class="line-content-wrapper">
              <!-- 位置高亮框 -->
              <span
                v-if="selection.valid && line.length > selection.startPos"
                class="position-highlight"
                :style="getHighlightStyle(line)"
              ></span>
              <!-- 日志内容 -->
              <span class="line-content">{{ line }}</span>
            </span>
          </div>
        </div>

        <div class="selection-info">
          <div class="current-selection">
            当前选择: 起始位置 {{ selection.startPos + 1 }} - 结束位置 {{ selection.endPos + 1 }}
            <span v-if="selectedText">(内容: "{{ selectedText }}")</span>
          </div>
          <a-button type="primary" :disabled="!selection.valid" @click="applySelection">
            应用选择
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'

interface Props {
  formData: {
    logTimeStart?: number
    logTimeEnd?: number
    logFilePath?: string
  }
  logFilePath?: string
  handleChange: (_section: string, _key: string, _value: any) => void
  rules: Record<string, any>
}

const props = defineProps<Props>()

// 视图模式 ('input' 或 'visual')
const viewMode = ref<'input' | 'visual'>('input')

// 日志预览相关
const logLines = ref<string[]>([])
const loadingPreview = ref(false)
const logPreviewRef = ref<HTMLDivElement | null>(null)

// 选择状态
const selection = reactive({
  active: false,
  startPos: 0,
  endPos: 0,
  startLineIndex: -1,
  endLineIndex: -1,
  valid: false,
})

// 监听formData的变化，确保选择状态与表单数据同步
watch(
  () => props.formData.logTimeStart,
  (newVal, oldVal) => {
    console.log('[LogTimestampSelector] logTimeStart changed:', { oldVal, newVal })
    if (newVal !== undefined && newVal !== null) {
      selection.startPos = newVal - 1 // 转换为0索引
    }
  },
  { immediate: true }
)

watch(
  () => props.formData.logTimeEnd,
  (newVal, oldVal) => {
    console.log('[LogTimestampSelector] logTimeEnd changed:', { oldVal, newVal })
    if (newVal !== undefined && newVal !== null) {
      selection.endPos = newVal - 1 // 转换为0索引
    }
  },
  { immediate: true }
)

// 当模式切换时，确保数据同步
const onViewModeChange = (e: any) => {
  const mode = e?.target?.value || e
  console.log('[LogTimestampSelector] onViewModeChange:', { mode, formData: props.formData })

  if (mode === 'visual') {
    // 切换到可视化模式时，将表单数据同步到选择状态
    selection.startPos = props.formData.logTimeStart ? props.formData.logTimeStart - 1 : 0
    selection.endPos = props.formData.logTimeEnd ? props.formData.logTimeEnd - 1 : 0
    selection.valid = !!props.formData.logTimeStart && !!props.formData.logTimeEnd
  }
  // 切换到输入模式时不需要特别处理，因为 formData 是通过 props 绑定的，
  // watch 会自动同步 selection 到 formData 的变化
}

// 计算属性
const selectedText = computed(() => {
  if (!selection.valid || selection.startLineIndex !== selection.endLineIndex) return ''

  const line = logLines.value[selection.startLineIndex]
  if (!line) return ''

  const start = Math.min(selection.startPos, selection.endPos)
  const end = Math.max(selection.startPos, selection.endPos)

  return line.substring(start, end + 1)
})

// 计算高亮框的样式（基于等宽字体的字符宽度）
const getHighlightStyle = (line: string) => {
  if (!selection.valid) return {}

  const start = Math.min(selection.startPos, selection.endPos)
  const end = Math.max(selection.startPos, selection.endPos)

  // 确保不超出当前行的长度
  const actualEnd = Math.min(end, line.length - 1)
  if (start >= line.length) return { display: 'none' }

  // 使用 ch 单位（等宽字体中一个字符的宽度）
  const charWidth = 1 // 1ch
  const left = start * charWidth
  const width = (actualEnd - start + 1) * charWidth

  return {
    left: `${left}ch`,
    width: `${width}ch`,
  }
}

// 鼠标抬起事件处理，获取文本选择范围
const handleMouseUp = () => {
  const selectionObj = window.getSelection()
  if (selectionObj && selectionObj.toString().trim() !== '') {
    const selectedText = selectionObj.toString()

    // 获取选择的起始和结束位置
    const range = selectionObj.getRangeAt(0)
    const startContainer = range.startContainer

    // 获取包含选择的行
    let startLineElement = startContainer.parentElement
    while (startLineElement && !startLineElement.classList.contains('log-line')) {
      startLineElement = startLineElement.parentElement
    }

    if (startLineElement) {
      const startLineIndex = parseInt(startLineElement.getAttribute('data-line-index') || '-1')

      if (startLineIndex >= 0 && startLineIndex < logLines.value.length) {
        const lineContentElement = startLineElement.querySelector('.line-content')
        if (!lineContentElement) {
          selection.valid = false
          return
        }

        // 获取原始文本
        const fullText = logLines.value[startLineIndex]

        // 使用 Range API 计算在渲染文本中的位置
        const tempRange = document.createRange()
        tempRange.selectNodeContents(lineContentElement)
        tempRange.setEnd(range.startContainer, range.startOffset)
        const startOffset = tempRange.toString().length
        const endOffset = startOffset + selectedText.length

        console.log('[LogTimestampSelector] 选择信息:', {
          selectedText,
          fullText,
          startOffset,
          endOffset,
          lineIndex: startLineIndex,
        })

        // 直接使用 DOM 计算的偏移量（纯文本模式下最精确）
        selection.startLineIndex = startLineIndex
        selection.endLineIndex = startLineIndex
        selection.startPos = startOffset
        selection.endPos = endOffset - 1
        selection.valid = true

        console.log('[LogTimestampSelector] 选择有效:', {
          'selection.startPos': selection.startPos,
          'selection.endPos': selection.endPos,
          'selected text': selectedText,
          'verified text': fullText.substring(selection.startPos, selection.endPos + 1),
        })
      } else {
        selection.valid = false
      }
    }
  } else {
    // 没有选择文本，重置选择
    selection.valid = false
  }
}

const handleMouseLeave = () => {
  // 当鼠标离开时，保持已选择的内容
}

// 加载日志文件
const loadLogFile = async () => {
  const targetPath = props.logFilePath

  if (!targetPath || targetPath.trim() === '') {
    message.warning('请先选择日志文件路径')
    return
  }

  try {
    loadingPreview.value = true

    // 使用Electron API读取文件
    if (window.electronAPI) {
      // 使用Electron API读取文件
      const content = await window.electronAPI.readFile(targetPath)

      if (!content) {
        message.warning('日志文件为空或无法读取')
        return
      }

      // 按行分割，但保持每行不换行显示
      logLines.value = content.split('\n').slice(0, 100) // 只加载前100行以提高性能

      // 过滤掉空行，但保留原索引映射
      logLines.value = logLines.value.filter(line => line.trim() !== '').slice(0, 50) // 进一步过滤并限制行数
    } else {
      // 如果没有Electron API可用，显示错误信息
      message.error('无法访问文件系统，请在Electron环境中使用此功能')
      return
    }

    message.success(`日志文件加载成功，共加载 ${logLines.value.length} 行`)
  } catch (error) {
    console.error('加载日志文件失败:', error)
    message.error('加载日志文件失败: ' + (error as Error).message)
  } finally {
    loadingPreview.value = false
  }
}

// 应用选择
const applySelection = async () => {
  if (!selection.valid) {
    message.warning('请先选择有效的日志时间戳范围')
    return
  }

  const startPos = selection.startPos + 1 // 转换为1索引
  const endPos = selection.endPos + 1 // 转换为1索引

  console.log('[LogTimestampSelector] 应用选择:', {
    startPos,
    endPos,
    'selection.startPos': selection.startPos,
    'selection.endPos': selection.endPos,
    'formData.logTimeStart before': props.formData.logTimeStart,
    'formData.logTimeEnd before': props.formData.logTimeEnd,
  })

  // 按顺序执行两次更新，避免竞态条件
  await props.handleChange('Script', 'LogTimeStart', startPos)
  console.log('[LogTimestampSelector] LogTimeStart 已更新')

  await props.handleChange('Script', 'LogTimeEnd', endPos)
  console.log('[LogTimestampSelector] LogTimeEnd 已更新')

  // 使用 setTimeout 确保在数据刷新后检查值
  setTimeout(() => {
    console.log('[LogTimestampSelector] 应用选择后:', {
      'formData.logTimeStart after': props.formData.logTimeStart,
      'formData.logTimeEnd after': props.formData.logTimeEnd,
    })
  }, 500)

  message.success(`已应用选择：起始位置 ${startPos}，结束位置 ${endPos}`)
}
</script>

<style scoped>
.log-timestamp-selector {
  width: 100%;
}

.visual-mode-container {
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  padding: 16px;
}

.log-preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.log-preview-area {
  position: relative;
  height: 300px;
  overflow: auto;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 8px;
  background-color: #fafafa;
  font-family: monospace;
  user-select: text; /* 启用文本选择 */
}

.log-line {
  position: relative;
  padding: 4px 8px;
  line-height: 1.5;
  cursor: text; /* 显示文本光标 */
  white-space: nowrap;
}

.log-line:hover {
  background-color: #e6f7ff;
}

.line-number {
  color: #ccc;
  margin-right: 8px;
  user-select: none;
}

.line-content-wrapper {
  position: relative;
  display: inline-block;
}

.position-highlight {
  position: absolute;
  top: 0;
  bottom: 0;
  background-color: rgba(24, 144, 255, 0.2);
  pointer-events: none;
  z-index: 0;
}

.line-content {
  position: relative;
  color: #333;
  white-space: nowrap;
  z-index: 1;
}

.selection-info {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.current-selection {
  color: #666;
}
</style>
