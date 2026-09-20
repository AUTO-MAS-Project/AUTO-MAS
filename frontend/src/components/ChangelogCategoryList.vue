<template>
  <section
    v-for="category in categories"
    :key="category.name"
    class="changelog-category"
    :class="`changelog-category--${category.kind}`"
  >
    <div class="changelog-category-title">
      <ExclamationCircleFilled v-if="category.kind === 'critical'" />
      <StarFilled v-else-if="category.kind === 'highlight'" />
      <span>{{ category.name }}</span>
    </div>
    <ul class="changelog-items">
      <!-- eslint-disable vue/no-v-html 更新说明来自 MAS 后端 / 仓库 version.json，属可信内容，且只做行内渲染 -->
      <li
        v-for="(item, index) in category.items"
        :key="index"
        class="changelog-item"
        v-html="renderInline(item)"
      ></li>
      <!-- eslint-enable vue/no-v-html -->
    </ul>
  </section>
</template>

<script setup lang="ts">
import { ExclamationCircleFilled, StarFilled } from '@ant-design/icons-vue'
import MarkdownIt from 'markdown-it'
import type { ChangelogCategory } from '@/utils/changelog'

defineProps<{
  /** 已按置顶规则排好序的分类列表（见 utils/changelog.ts 的 orderCategories） */
  categories: ChangelogCategory[]
}>()

// 结构由模板搭，只有单条文本走行内 Markdown（条目末尾常带 by [@user](url) 链接）
const md = new MarkdownIt({ html: true, linkify: true, typographer: true })
const renderInline = (text: string) => md.renderInline(text)
</script>

<style scoped>
.changelog-category {
  margin: 8px 0 12px;
}

.changelog-category-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.changelog-items {
  margin: 0;
  padding-left: 22px;
}

.changelog-item {
  margin: 2px 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.changelog-item :deep(a) {
  color: var(--ant-color-primary);
}

/* 破坏性变更：警示色块，最醒目 */
.changelog-category--critical {
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--ant-color-warning-bg);
  border: 1px solid var(--ant-color-warning);
}

.changelog-category--critical .changelog-category-title {
  color: var(--ant-color-warning);
}

/* 本次亮点：主题强调色，次醒目 */
.changelog-category--highlight {
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--ant-color-primary-bg);
  border: 1px solid var(--ant-color-primary-border);
}

.changelog-category--highlight .changelog-category-title {
  color: var(--ant-color-primary);
}
</style>
