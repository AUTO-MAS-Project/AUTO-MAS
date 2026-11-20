<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CaretDownOutlined, CaretUpOutlined } from '@ant-design/icons-vue'
import MarkdownIt from 'markdown-it'
import type { PluginReleaseNote } from '@/api/models/PluginReleaseNote'

defineProps<{ notes: readonly PluginReleaseNote[]; upgrade?: boolean }>()
const { t } = useI18n()
const open = ref(false)
// 插件正文来自外部仓库，只展示排版和文本，不加载外部图片或提供页内导航。
const markdown = new MarkdownIt({ html: false }).disable(['image', 'link', 'autolink', 'reference'])
</script>

<template>
  <div v-if="notes.length || $slots.default" class="plugin-release-notes">
    <div class="release-notes-header">
      <slot />
      <a-button
        v-if="notes.length"
        type="link"
        size="small"
        :aria-expanded="open"
        @click="open = !open"
      >
        {{ t('core.plugins.releaseNotes') }}
        <CaretUpOutlined v-if="open" /><CaretDownOutlined v-else />
      </a-button>
    </div>
    <div v-if="open && notes.length" class="release-notes-body">
      <section v-for="note in notes" :key="note.version">
        <strong>{{ note.version }}</strong>
        <!-- eslint-disable-next-line vue/no-v-html -- Markdown 关闭 HTML、图片和链接，文本由渲染器转义。 -->
        <div class="release-markdown" v-html="markdown.render(note.body)" />
      </section>
      <small v-if="upgrade">{{ t('core.plugins.releaseNotesLimit') }}</small>
    </div>
  </div>
</template>

<style scoped>
.release-notes-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.plugin-release-notes {
  min-width: 0;
}
.release-notes-body {
  padding: 8px 8px 0;
  overflow-wrap: anywhere;
}
.release-notes-body section + section {
  margin-top: 12px;
}
.release-notes-body small {
  color: var(--ant-color-text-secondary);
}
.release-markdown :deep(ul),
.release-markdown :deep(ol) {
  padding-inline-start: 20px;
}
.release-markdown :deep(p),
.release-markdown :deep(ul),
.release-markdown :deep(ol) {
  margin-block: 4px;
}
.release-markdown :deep(pre) {
  white-space: pre-wrap;
}
</style>
