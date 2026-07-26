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
        <span class="field-label">鹰角网络通行证登录凭证</span>
        <div class="sensitive-field">
          <a-input-password
            :value="tokenDraft"
            :disabled="loading || !formData.Info.IfSkland"
            :placeholder="tokenPlaceholder"
            size="large"
            autocomplete="new-password"
            @update:value="tokenDraft = $event"
          />
          <div class="sensitive-actions">
            <span class="sensitive-hint">已保存凭证不会回显；仅在明确点击时替换或清空</span>
            <a-space size="small">
              <a-button
                v-if="hasStoredToken"
                size="small"
                danger
                :disabled="loading || !formData.Info.IfSkland"
                @click="clearToken"
              >
                清空原值
              </a-button>
              <a-button
                type="primary"
                size="small"
                :disabled="loading || !formData.Info.IfSkland || !tokenDraft"
                @click="saveToken"
              >
                保存新值
              </a-button>
            </a-space>
          </div>
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import { handleExternalLink } from '@/utils/openExternal'

const props = defineProps<{
  formData: any
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
  sensitiveSave: [key: 'Info.SklandToken', intent: 'replace' | 'clear', value?: string]
}>()

const tokenDraft = ref('')
const hasStoredToken = computed(() => Boolean(props.formData?.Info?.SklandToken))
const tokenPlaceholder = computed(() =>
  hasStoredToken.value ? '已保存；留空保持原值，输入新值后明确保存' : '请输入登录凭证'
)

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const saveToken = () => {
  if (!tokenDraft.value) return
  emit('sensitiveSave', 'Info.SklandToken', 'replace', tokenDraft.value)
}

const clearToken = () => {
  Modal.confirm({
    title: '清空森空岛登录凭证？',
    content: '清空后自动签到将无法登录，直到重新填写凭证。',
    okText: '清空',
    cancelText: '取消',
    okType: 'danger',
    centered: true,
    onOk: () => emit('sensitiveSave', 'Info.SklandToken', 'clear', ''),
  })
}

defineExpose({
  resetTokenDraft: () => {
    tokenDraft.value = ''
  },
})
</script>

<style scoped>
.form-section {
  margin-bottom: var(--v6-space-4);
}

.section-header {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-doc-link {
  color: var(--v6-color-text-link) !important;
  text-decoration: none;
  font-size: var(--v6-font-size-base);
  font-weight: 500;
  padding: 4px 8px;
  border-radius: var(--v6-radius-sm);
  border: 1px solid var(--v6-color-border);
  transition: all var(--v6-motion-fast) var(--v6-ease-out);
  display: flex;
  align-items: center;
  gap: 4px;
}

.section-doc-link:hover {
  color: var(--v6-color-text-link-hover) !important;
  background-color: var(--v6-vibrancy-hover);
  border-color: var(--v6-color-info);
  text-decoration: none;
}

.switch-description {
  margin-left: var(--v6-space-3);
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
}

.field-label {
  font-weight: var(--v6-font-weight-medium);
}

.sensitive-field {
  display: grid;
  gap: var(--v6-space-2);
  margin-top: var(--v6-space-2);
}

.sensitive-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
}

.sensitive-hint {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}

@media (max-width: 768px) {
  .sensitive-actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
