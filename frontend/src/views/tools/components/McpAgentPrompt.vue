<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CopyOutlined } from '@ant-design/icons-vue'

const props = defineProps<{ address: string }>()
const { t } = useI18n()
const copying = ref(false)
const prompt = computed(() => t('core.tools.mcp.agentPrompt', { address: props.address }))

async function copyPrompt() {
  copying.value = true
  try {
    await navigator.clipboard.writeText(prompt.value)
    message.success(t('core.tools.mcp.promptCopied'))
  } catch {
    message.error(t('core.comp.copyFailed'))
  } finally {
    copying.value = false
  }
}
</script>

<template>
  <section class="mcp-agent-prompt" :aria-label="t('core.tools.mcp.agentPromptTitle')">
    <a-flex align="center" justify="space-between" wrap="wrap" :gap="12">
      <h3 class="mcp-agent-prompt-title">{{ t('core.tools.mcp.agentPromptTitle') }}</h3>
      <a-button :loading="copying" @click="copyPrompt">
        <template #icon><CopyOutlined aria-hidden="true" /></template>
        {{ t('core.tools.mcp.copyPrompt') }}
      </a-button>
    </a-flex>
    <a-textarea
      :value="prompt"
      :aria-label="t('core.tools.mcp.agentPromptTitle')"
      :auto-size="{ minRows: 9, maxRows: 14 }"
      :spellcheck="false"
      readonly
    />
  </section>
</template>

<style scoped>
.mcp-agent-prompt {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 24px;
}

.mcp-agent-prompt-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
</style>
