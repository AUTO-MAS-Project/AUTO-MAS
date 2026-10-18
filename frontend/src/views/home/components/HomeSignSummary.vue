<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { HomeModuleKey } from '@/types/home'
import { escapeSignMarkdown, type GameSignSummary, type GameSignUser } from '../signStats'

const props = defineProps<{
  gameKey: HomeModuleKey | null
  summary: GameSignSummary
  users: GameSignUser[]
  loading: boolean
  error: boolean
  showRefresh: boolean
}>()
defineEmits<{ refresh: [] }>()
const { t } = useI18n()
const expanded = ref(false)
const DEFAULT_VISIBLE_USERS = 3
const md = new MarkdownIt({ html: false, linkify: false, breaks: true })
const visibleUsers = computed(() =>
  expanded.value ? props.users : props.users.slice(0, DEFAULT_VISIBLE_USERS)
)
const hiddenCount = computed(() => Math.max(0, props.users.length - DEFAULT_VISIBLE_USERS))
watch(
  () => props.gameKey,
  () => {
    expanded.value = false
  }
)

const renderUser = (user: GameSignUser) => {
  const name = escapeSignMarkdown(user.name || t('home.activityNotes.user'))
  const entries = user.entries.map(entry => {
    // 中文状态是后端合同值，翻译只用于最终展示。
    const status =
      entry.status === '成功'
        ? t('home.activityNotes.signed')
        : entry.status === '已签到'
          ? t('home.activityNotes.alreadySigned')
          : entry.status === '失败'
            ? t('home.activityNotes.failed')
            : entry.status
    return [status, entry.reward, entry.reason].filter(Boolean).map(escapeSignMarkdown).join(' ')
  })
  const detail = entries.length
    ? entries.join('；')
    : escapeSignMarkdown(t('home.activityNotes.noRecord'))
  return md.renderInline(`**${name}**：${detail}`)
}
</script>

<template>
  <div class="sign-summary">
    <div class="sign-heading">
      <CheckCircleOutlined :class="summary.signed === summary.total ? 'is-signed' : 'is-pending'" />
      <strong>{{
        t('home.activityNotes.sign', { signed: summary.signed, total: summary.total })
      }}</strong>
      <a-button
        v-if="showRefresh"
        type="text"
        size="small"
        :loading="loading"
        :aria-label="t('gamesign.activity.refresh')"
        @click="$emit('refresh')"
        ><ReloadOutlined
      /></a-button>
    </div>
    <!-- eslint-disable vue/no-v-html Markdown 禁用 HTML 和自动链接，所有外部文本均转义。 -->
    <div v-for="user in visibleUsers" :key="user.uid" class="sign-user" v-html="renderUser(user)" />
    <!-- eslint-enable vue/no-v-html -->
    <a-button
      v-if="hiddenCount"
      class="sign-expand"
      type="link"
      size="small"
      @click="expanded = !expanded"
    >
      {{
        expanded
          ? t('home.activityNotes.collapse')
          : t('home.activityNotes.expand', { count: hiddenCount })
      }}
    </a-button>
    <span v-if="error" class="sign-error">{{ t('home.activityNotes.signFailed') }}</span>
  </div>
</template>

<style scoped>
.sign-summary {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}
.sign-heading {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text);
  font-size: 14px;
}
.sign-user {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.sign-user :deep(strong) {
  color: var(--ant-color-text);
  font-weight: 500;
}
.sign-expand {
  align-self: flex-start;
  padding: 0;
  height: auto;
}
.sign-error,
.is-pending {
  color: var(--ant-color-text-tertiary);
}
.is-signed {
  color: var(--ant-color-success);
}
</style>
