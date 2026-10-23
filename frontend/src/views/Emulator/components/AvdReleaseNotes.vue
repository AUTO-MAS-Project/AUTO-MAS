<script setup lang="ts">
/**
 * 魔改 AVD 新版本的更新公告。
 *
 * 跳了几版时先把各版的一句话摘要合起来列出（来自公告第一行的机读行），再显示最新一版的公告正文
 * （后端已截到分隔行以上）。正文来自 GitHub Release，按 Markdown 渲染、不认 HTML，链接用系统浏览器打开。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'

import type { Emulator2AvdChangeEntry } from '@/api'
import { showMergedChanges, versionLabel } from '../avdLogic'

const props = defineProps<{
  changes: Emulator2AvdChangeEntry[]
  announcement: string
  latest: string
  releaseUrl: string
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')

// html: false：公告来自外部仓库，原样的 HTML 一律当文本显示
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: false })

const merged = computed(() => showMergedChanges(props.changes))
const announcementHtml = computed(() =>
  props.announcement.trim() ? markdown.render(props.announcement) : ''
)

const openLink = async (url: string) => {
  if (!/^https?:\/\//i.test(url)) return
  const result = await window.electronAPI?.openUrl?.(url)
  if (result && !result.success) logger.warn(`打开链接失败: ${url} ${result.error ?? ''}`)
}

const onContentClick = (event: MouseEvent) => {
  const link = (event.target as HTMLElement | null)?.closest('a') as HTMLAnchorElement | null
  if (!link?.href) return
  event.preventDefault()
  void openLink(link.href)
}
</script>

<template>
  <div class="avd-release-notes">
    <template v-if="merged">
      <div class="notes-title">{{ t('emulator2.avd.update.changesTitle') }}</div>
      <section v-for="entry in changes" :key="entry.version" class="notes-version">
        <div class="notes-version-title">{{ versionLabel(entry.label, entry.version) }}</div>
        <div v-for="group in entry.groups ?? []" :key="group.category" class="notes-group">
          <span class="notes-category">{{ group.category }}</span>
          <ul class="notes-items">
            <li v-for="(item, index) in group.items ?? []" :key="index">{{ item }}</li>
          </ul>
        </div>
      </section>
    </template>
    <template v-if="announcementHtml">
      <div class="notes-title">
        {{ t('emulator2.avd.update.announcementTitle', { version: latest }) }}
      </div>
      <!-- eslint-disable vue/no-v-html -- markdown-it 关了 html，正文里的 HTML 只会被转义成文本 -->
      <div class="notes-body" @click="onContentClick" v-html="announcementHtml" />
      <!-- eslint-enable vue/no-v-html -->
    </template>
    <a v-if="releaseUrl" class="notes-link" href="#" @click.prevent="openLink(releaseUrl)">
      {{ t('emulator2.avd.update.releasePage') }}
    </a>
  </div>
</template>

<style scoped>
.avd-release-notes {
  max-height: 260px;
  overflow-y: auto;
  padding: 8px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.notes-title {
  margin: 4px 0;
  font-weight: 600;
}

.notes-version + .notes-version {
  margin-top: 6px;
}

.notes-version-title {
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.notes-group {
  display: flex;
  gap: 8px;
}

.notes-category {
  flex-shrink: 0;
  color: var(--ant-color-text-tertiary);
}

.notes-items {
  margin: 0;
  padding-left: 16px;
}

.notes-body :deep(h2) {
  margin: 10px 0 4px;
  font-size: 14px;
  font-weight: 600;
}

.notes-body :deep(h3) {
  margin: 8px 0 2px;
  font-size: 13px;
  font-weight: 600;
}

.notes-body :deep(p) {
  margin: 0 0 6px;
}

.notes-body :deep(ul) {
  margin: 0 0 6px;
  padding-left: 18px;
}

.notes-body :deep(a),
.notes-link {
  color: var(--ant-color-primary);
}

.notes-body :deep(code) {
  padding: 0 4px;
  border-radius: 4px;
  background: var(--ant-color-fill-quaternary);
}
</style>
