<template>
  <div class="form-section">
    <div class="section-header">
      <h3>森空岛配置</h3>
      <a
        href="https://doc.auto-mas.top/docs/script-guide/maa.html#%E6%A3%AE%E7%A9%BA%E5%B2%9B%E8%87%AA%E5%8A%A8%E7%AD%BE%E5%88%B0"
        class="section-doc-link"
        title="查看森空岛签到配置文档"
        @click="handleExternalLink"
      >
        文档
      </a>
    </div>
    <a-row :gutter="24" align="middle">
      <a-col :span="6">
        <span style="font-weight: 500">森空岛签到</span>
      </a-col>
      <a-col :span="18">
        <a-switch
          v-model:checked="formData.Info.IfSkland"
          :disabled="loading"
          @change="emitSave('Info.IfSkland', formData.Info.IfSkland)"
        />
        <span class="switch-description">开启后将启用森空岛签到功能</span>
      </a-col>
    </a-row>
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="24">
        <span style="font-weight: 500">鹰角网络通行证登录凭证</span>
        <div class="sensitive-field-row" style="margin-top: 8px">
          <a-input-password
            :value="tokenDraft"
            :placeholder="tokenPlaceholder"
            :disabled="loading || !formData.Info.IfSkland"
            size="large"
            autocomplete="new-password"
            style="width: 100%"
            @update:value="(val: string) => handleTokenInput(val)"
            @blur="handleTokenBlur"
          />
          <a-button
            v-if="!loading && formData.Info.IfSkland && hasStoredToken"
            size="small"
            type="link"
            danger
            :disabled="tokenExplicitlyCleared"
            @click="handleClearToken"
          >
            {{ tokenExplicitlyCleared ? '已清空' : '清空原值' }}
          </a-button>
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { handleExternalLink } from '@/utils/openExternal'

const props = defineProps<{
  formData: any
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
  /**
   * 敏感字段保存意图（与 BasicInfoSection 一致，Lane 06 任务书第 2 条）：
   * - `keep`：未触碰 → 不发送给后端。
   * - `replace`：输入新值 → 发送新明文。
   * - `clear`：显式清空 → 发送空串 `""`。
   */
  sensitiveSave: [key: string, intent: 'keep' | 'replace' | 'clear', value?: string]
  sensitiveDirtyChange: [key: string, dirty: boolean]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

// ============================================================
// SklandToken 敏感字段：草稿驱动，不在 DOM 显示明文
// ============================================================

const tokenDraft = ref('')
const tokenExplicitlyCleared = ref(false)

const hasStoredToken = computed(() => {
  const stored = props.formData?.Info?.SklandToken
  return typeof stored === 'string' && stored.length > 0
})

const tokenPlaceholder = computed(() => {
  if (tokenExplicitlyCleared.value) {
    return '已清空。留空保持清空状态，输入新值替换'
  }
  if (hasStoredToken.value) {
    return '已保存。留空保持原值，输入新值替换'
  }
  return '请输入鹰角网络通行证登录凭证'
})

const handleTokenInput = (val: string) => {
  tokenDraft.value = val
  if (val !== '' && tokenExplicitlyCleared.value) {
    tokenExplicitlyCleared.value = false
  }
  emit('sensitiveDirtyChange', 'Info.SklandToken', val !== '' || tokenExplicitlyCleared.value)
}

const handleClearToken = () => {
  if (!hasStoredToken.value) {
    return
  }
  tokenDraft.value = ''
  tokenExplicitlyCleared.value = true
  emit('sensitiveDirtyChange', 'Info.SklandToken', true)
}

const handleTokenBlur = () => {
  if (tokenExplicitlyCleared.value) {
    emit('sensitiveSave', 'Info.SklandToken', 'clear', '')
    return
  }
  if (tokenDraft.value === '') {
    emit('sensitiveSave', 'Info.SklandToken', 'keep')
    return
  }
  emit('sensitiveSave', 'Info.SklandToken', 'replace', tokenDraft.value)
}

watch(
  () => props.formData?.Info?.SklandToken,
  () => {
    tokenDraft.value = ''
    tokenExplicitlyCleared.value = false
    emit('sensitiveDirtyChange', 'Info.SklandToken', false)
  }
)

defineExpose({
  resetTokenDraft: () => {
    tokenDraft.value = ''
    tokenExplicitlyCleared.value = false
  },
  isTokenDirty: () => tokenDraft.value !== '' || tokenExplicitlyCleared.value,
})
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.section-doc-link {
  color: var(--ant-color-primary) !important;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--ant-color-primary);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.section-doc-link:hover {
  color: var(--ant-color-primary-hover) !important;
  background-color: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-hover);
  text-decoration: none;
}

.switch-description {
  margin-left: 12px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.sensitive-field-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.sensitive-field-row :deep(.ant-input-password) {
  width: 100%;
}

.sensitive-field-row :deep(.ant-btn-link) {
  padding: 0;
  height: auto;
  font-size: 12px;
  line-height: 1.5;
}
</style>
