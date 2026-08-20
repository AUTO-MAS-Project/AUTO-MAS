<script setup lang="ts">
import { BugOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { computed, reactive, watch } from 'vue'
import { useLogPatternDebug } from '../composables/useLogPatternDebug'
import type { PushLogPattern } from '../composables/usePushLogPatterns'

const props = defineProps<{
  open: boolean
  pattern: PushLogPattern | null
  logPath?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

// 用 reactive 包裹，使模板中的 debug.input / debug.results 等嵌套 ref 自动解包；
// logPath 需传 getter，否则 setup 只捕获初始值（.），异步加载脚本后仍读旧值导致「加载日志」误判未配置路径
const debug = reactive(useLogPatternDebug({ logPath: () => props.logPath }))

// 将弹窗接收到的规则配置同步到本实例，供 runDebug / isMultiline 使用；
// 切到不同规则时清空上一次的结果（避免残留上一规则的结果误导），但保留日志输入供跨规则复用
watch(
  () => props.pattern,
  (pat, prev) => {
    debug.currentPattern = pat
    if (prev) {
      debug.results = []
      debug.compileError = null
    }
  },
  { immediate: true },
)

const title = computed(() => {
  if (!props.pattern) return '规则调试'
  const name = props.pattern.name?.trim()
  return name ? `规则调试 - ${name}` : '规则调试'
})

const configPreview = computed(() => {
  const item = props.pattern
  if (!item) return ''
  if (item.type === 'split') {
    return `[split] match="${item.match || ''}" head="${item.head || ''}"(含${item.headInclude ? '是' : '否'}) tail="${item.tail || ''}"(含${item.tailInclude ? '是' : '否'})`
  }
  if (item.type === 'regex') {
    return `[regex] match="${item.match || ''}" extract="${item.extract || ''}"`
  }
  return `[multiline] start="${item.start || ''}" end="${item.end || ''}" extract="${item.extract || ''}" maxLines=${item.maxLines || 50}`
})
</script>

<template>
  <a-modal
    :open="open"
    :title="title"
    width="900px"
    :footer="null"
    :destroy-on-close="true"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <template #title>
      <span class="modal-title">
        <BugOutlined />
        {{ title }}
      </span>
    </template>

    <div class="debug-body">
      <!-- 左侧：输入 -->
      <div class="debug-input-pane">
        <div class="debug-config-preview">
          <FileTextOutlined />
          <code class="debug-config-code">{{ configPreview }}</code>
        </div>

        <div class="debug-toolbar">
          <span class="debug-section-label">待调试日志</span>
          <div class="debug-toolbar-actions">
            <a-input-number
              v-model:value="debug.logLines"
              size="small"
              :min="-1"
              :step="100"
              style="width: 80px"
            />
            <span class="debug-toolbar-hint">行</span>
            <a-button
              type="primary"
              size="small"
              :loading="debug.loadingLog"
              :disabled="!logPath || logPath === '.'"
              @click="debug.loadLog"
            >
              加载日志
            </a-button>
          </div>
        </div>

        <a-textarea
          v-model:value="debug.input"
          :rows="14"
          placeholder="粘贴要测试的日志行，每行一条..."
          class="debug-textarea"
        />

        <div class="debug-actions">
          <a-button
            type="primary"
            :loading="debug.running"
            :disabled="!debug.input.trim()"
            @click="debug.runDebug"
          >
            <template #icon>
              <BugOutlined />
            </template>
            调试
          </a-button>
          <a-button @click="debug.clear">清空</a-button>
        </div>
      </div>

      <!-- 右侧：结果 -->
      <div class="debug-result-pane">
        <div class="debug-result-header">
          <span class="debug-section-label">
            结果（{{ debug.hitCount }}/{{ debug.results.length }}）
          </span>
          <a-checkbox v-model:checked="debug.onlyHit" size="small">
            仅显示已命中
          </a-checkbox>
        </div>

        <a-alert
          v-if="debug.compileError"
          type="error"
          show-icon
          class="debug-compile-error"
          :message="debug.compileError"
          closable
          @close="debug.compileError = null"
        />

        <div v-if="debug.results.length > 0" class="debug-results-list">
          <div
            v-for="item in debug.filteredResults"
            :key="item.idx"
            :class="['debug-result-item', item.hit ? 'hit' : 'miss']"
          >
            <div class="debug-result-line">
              <span class="debug-result-line-num">{{ item.idx + 1 }}</span>
              <span v-if="!debug.isMultiline" class="debug-result-line-text">{{ item.line }}</span>
              <span v-else class="debug-result-line-text">窗口 {{ item.idx + 1 }}</span>
            </div>
            <div class="debug-result-out">
              <a-tag v-if="item.hit" color="green" class="debug-result-tag">命中</a-tag>
              <a-tag v-else color="default" class="debug-result-tag">未命中</a-tag>
              <span v-if="item.hit" class="debug-result-extracted">{{ item.extracted }}</span>
              <span v-else-if="item.error" class="debug-result-error">{{ item.error }}</span>
            </div>
          </div>
          <div v-if="debug.filteredResults.length === 0" class="debug-results-empty">
            无命中行
          </div>
        </div>

        <div v-else class="debug-results-empty">
          点击「调试」查看匹配结果
        </div>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.modal-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.debug-body {
  display: flex;
  gap: 16px;
  height: 60vh;
  min-height: 420px;
}

.debug-input-pane,
.debug-result-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.debug-config-preview {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  background: var(--ant-color-fill-tertiary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.debug-config-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: var(--ant-color-text-secondary);
  word-break: break-all;
  line-height: 1.5;
}

.debug-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.debug-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.debug-toolbar-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.debug-section-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.debug-textarea {
  flex: 1;
  min-height: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  resize: none;
}

.debug-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.debug-result-pane {
  border-left: 1px solid var(--ant-color-border-secondary);
  padding-left: 16px;
}

.debug-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.debug-compile-error {
  margin-bottom: 12px;
}

.debug-results-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.debug-results-empty {
  padding: 40px 8px;
  text-align: center;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.debug-result-item {
  padding: 8px 10px;
  margin-bottom: 8px;
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.debug-result-item.hit {
  background: var(--ant-color-success-bg);
  border-color: var(--ant-color-success-border);
}

.debug-result-item.miss {
  background: var(--ant-color-fill-quaternary);
  opacity: 0.8;
}

.debug-result-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 4px;
}

.debug-result-line-num {
  flex-shrink: 0;
  min-width: 20px;
  height: 20px;
  border-radius: 10px;
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
}

.debug-result-line-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--ant-color-text);
  word-break: break-all;
  line-height: 1.5;
  flex: 1;
}

.debug-result-out {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-left: 28px;
}

.debug-result-tag {
  flex-shrink: 0;
  margin: 0;
  margin-top: 1px;
}

.debug-result-extracted {
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--ant-color-success);
  white-space: pre-wrap;
  word-break: break-all;
  font-weight: 500;
  line-height: 1.6;
}

.debug-result-error {
  font-size: 12px;
  color: var(--ant-color-error);
}

@media (prefers-color-scheme: dark) {
  .debug-result-pane {
    border-left-color: var(--ant-color-border);
  }
}
</style>
