<template>
  <div class="maafw-description-view">
    <!-- eslint-disable vue/no-v-html -- HTML is sanitized by sanitizeHtml before rendering. -->
    <div v-if="renderedHtml" @click="handleContentClick" v-html="renderedHtml" />
    <!-- eslint-enable vue/no-v-html -->
    <a-modal v-model:open="previewOpen" :footer="null" centered width="80%">
      <img
        v-if="previewImage"
        :src="previewImage"
        alt=""
        loading="lazy"
        class="description-preview-image"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'

const props = withDefaults(
  defineProps<{
    content?: string | null
    basePath?: string
  }>(),
  {
    content: '',
    basePath: '',
  }
)

const markdown = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: true,
})

const previewOpen = ref(false)
const previewImage = ref('')

const renderedHtml = computed(() => {
  const content = props.content?.trim()
  if (!content) return ''
  return sanitizeHtml(markdown.render(content))
})

const allowedTags = new Set([
  'a',
  'blockquote',
  'br',
  'code',
  'div',
  'em',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'img',
  'li',
  'ol',
  'p',
  'pre',
  'span',
  'strong',
  'table',
  'tbody',
  'td',
  'th',
  'thead',
  'tr',
  'ul',
])

const allowedAttrs: Record<string, Set<string>> = {
  a: new Set(['href', 'title', 'target', 'rel']),
  img: new Set(['alt', 'src', 'title']),
  code: new Set(['class']),
  span: new Set(['class']),
  div: new Set(['class']),
}

const sanitizeHtml = (html: string) => {
  const documentRef = new DOMParser().parseFromString(html, 'text/html')

  const walk = (node: Node) => {
    for (const child of Array.from(node.childNodes)) {
      if (!(child instanceof Element)) continue

      const tagName = child.tagName.toLowerCase()
      if (!allowedTags.has(tagName)) {
        child.replaceWith(documentRef.createTextNode(child.textContent || ''))
        continue
      }

      for (const attr of Array.from(child.attributes)) {
        const attrName = attr.name.toLowerCase()
        if (attrName === 'style') {
          child.removeAttribute(attr.name)
          continue
        }
        const tagAttrs = allowedAttrs[tagName]
        if (!tagAttrs?.has(attrName)) {
          child.removeAttribute(attr.name)
        }
      }

      if (tagName === 'a') {
        const href = normalizeLinkUrl(child.getAttribute('href') || '')
        if (!href) {
          child.removeAttribute('href')
        } else {
          child.setAttribute('href', href)
          child.setAttribute('target', '_blank')
          child.setAttribute('rel', 'noreferrer noopener')
        }
      }

      if (tagName === 'img') {
        const src = normalizeImageUrl(child.getAttribute('src') || '')
        if (!src) {
          child.remove()
          continue
        }
        child.setAttribute('src', src)
        child.setAttribute('loading', 'lazy')
        child.setAttribute('decoding', 'async')
      }

      walk(child)
    }
  }

  walk(documentRef.body)
  return documentRef.body.innerHTML
}

const normalizeLinkUrl = (rawUrl: string) => {
  const value = rawUrl.trim()
  if (/^(https?:|mailto:)/i.test(value)) return value
  return ''
}

const normalizeImageUrl = (rawUrl: string) => {
  const value = rawUrl.trim()
  if (/^(https?:|data:image\/)/i.test(value)) return value
  return buildMaaFWAssetUrl(props.basePath, value)
}

const handleContentClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement | null
  const image = target?.closest('img') as HTMLImageElement | null
  if (image?.src) {
    previewImage.value = image.src
    previewOpen.value = true
    return
  }

  const link = target?.closest('a') as HTMLAnchorElement | null
  if (!link?.href) return

  event.preventDefault()
  window.electronAPI?.openUrl?.(link.href)
}
</script>

<style scoped>
.maafw-description-view {
  color: var(--ant-color-text);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.maafw-description-view :deep(p) {
  margin: 0 0 8px;
}

.maafw-description-view :deep(p:last-child) {
  margin-bottom: 0;
}

.maafw-description-view :deep(img) {
  max-width: 100%;
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary);
  cursor: zoom-in;
}

.maafw-description-view :deep(pre) {
  padding: 8px 12px;
  overflow: auto;
  border-radius: 6px;
  background: var(--ant-color-fill-quaternary);
}

.description-preview-image {
  display: block;
  max-width: 100%;
  max-height: 78vh;
  margin: 0 auto;
}
</style>
