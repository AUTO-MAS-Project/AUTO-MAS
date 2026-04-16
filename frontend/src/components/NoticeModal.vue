<template>
  <a-modal v-model:open="visible" title="绯荤粺鍏憡" :width="800" :footer="null" :closable="false" :mask-closable="false"
    class="notice-modal">
    <div v-if="notices.length > 0" class="notice-container">
      <!-- 鍏憡鏍囩椤?- 绔栫洿甯冨眬 -->
      <a-tabs v-model:active-key="activeNoticeKey" tab-position="left" class="notice-tabs"
        :tab-bar-style="{ width: '200px' }">
        <a-tab-pane v-for="(content, title) in noticeData" :key="title" :tab="title" class="notice-tab-pane">
          <div class="notice-content">
            <div ref="markdownContentRef" class="markdown-content" @click="handleLinkClick"
              v-html="renderMarkdown(content)"></div>
          </div>
        </a-tab-pane>
      </a-tabs>

      <!-- 搴曢儴鎿嶄綔鎸夐挳 -->
      <div class="notice-footer">
        <div class="notice-pagination">
          <span class="pagination-text"> 鍏?{{ notices.length }} 涓叕鍛?</span>
        </div>

        <div class="notice-actions">
          <a-button type="primary" :loading="confirming" class="confirm-button" @click="confirmNotices">
            鎴戠煡閬撲簡
          </a-button>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import MarkdownIt from 'markdown-it'
import { infoApi } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = window.electronAPI.getLogger('鍏憡妯℃€佹')

interface Props {
  visible: boolean
  noticeData: Record<string, string>
}

interface Emits {
  (e: 'update:visible', visible: boolean): void
  (e: 'confirmed'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value),
})

const confirming = ref(false)
const activeNoticeKey = ref('')

// 闊抽鎾斁鍣?
const { playSound } = useAudioPlayer()

// 鍒濆鍖?markdown 瑙ｆ瀽鍣?
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
})

// 鑾峰彇鍏憡鏍囬鍒楄〃
const notices = computed(() => Object.keys(props.noticeData))

// 褰撳墠鍏憡绱㈠紩
computed(() => {
  return notices.value.findIndex(title => title === activeNoticeKey.value)
})
// 娓叉煋 markdown
const renderMarkdown = (content: string) => {
  return md.render(content)
}

// 纭鎵€鏈夊叕鍛?
const confirmNotices = async () => {
  confirming.value = true
  try {
    const response = await infoApi.confirmNotice()
    if (response.code === 200) {
      visible.value = false
      emit('confirmed')
    } else {
      message.error(response.message || '纭鍏憡澶辫触')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`纭鍏憡澶辫触: ${errorMsg}`)
    message.error('纭鍏憡澶辫触锛岃閲嶈瘯')
  } finally {
    confirming.value = false
  }
}

// 澶勭悊閾炬帴鐐瑰嚮
const handleLinkClick = async (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (target.tagName === 'A') {
    event.preventDefault()
    const url = target.getAttribute('href')
    if (url) {
      try {
        // 妫€鏌ユ槸鍚﹀湪Electron鐜涓?
        if (window.electronAPI && window.electronAPI.openUrl) {
          const result = await window.electronAPI.openUrl(url)
          if (!result.success) {
            logger.error(`鎵撳紑閾炬帴澶辫触: ${String(result.error)}`)
            message.error('鎵撳紑閾炬帴澶辫触锛岃鎵嬪姩澶嶅埗閾炬帴鍦板潃')
          }
        } else {
          // 濡傛灉涓嶅湪Electron鐜涓紝浣跨敤鏅€氱殑window.open
          window.open(url, '_blank')
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`鎵撳紑閾炬帴澶辫触: ${errorMsg}`)
        message.error('鎵撳紑閾炬帴澶辫触锛岃鎵嬪姩澶嶅埗閾炬帴鍦板潃')
      }
    }
  }
}

// 鐩戝惉鍏憡鏁版嵁鍙樺寲锛岃缃粯璁ら€変腑绗竴涓叕鍛?
watch(
  () => props.noticeData,
  newData => {
    const titles = Object.keys(newData)
    if (titles.length > 0 && !activeNoticeKey.value) {
      activeNoticeKey.value = titles[0]
    }
  },
  { immediate: true }
)

// 鐩戝惉寮圭獥鏄剧ず鐘舵€侊紝閲嶇疆鍒扮涓€涓叕鍛婂苟鎾斁闊抽
watch(visible, async newVisible => {
  if (newVisible && notices.value.length > 0) {
    activeNoticeKey.value = notices.value[0]
    // 褰撳叕鍛婃ā鎬佹鏄剧ず鏃舵挱鏀鹃煶棰?
    await playSound('announcement_display')
  }
})
</script>

<style scoped>
.notice-modal :deep(.ant-modal-body) {
  padding: 16px 24px;
  max-height: 70vh;
  overflow: hidden;
}

.notice-container {
  display: flex;
  flex-direction: column;
  height: 60vh;
}

.notice-tabs {
  flex: 1;
  min-height: 0;
}

.notice-tabs :deep(.ant-tabs-tab-list) {
  width: 200px;
}

.notice-tabs :deep(.ant-tabs-tab) {
  text-align: left;
  padding: 8px 16px;
}

.notice-tabs :deep(.ant-tabs-content-holder) {
  max-height: 50vh;
  overflow-y: auto;
  padding-left: 16px;
  /* 闅愯棌婊氬姩鏉′絾淇濇寔婊氬姩鍔熻兘 */
  scrollbar-width: none;
  /* Firefox */
  -ms-overflow-style: none;
  /* IE 鍜?Edge */
}

/* 闅愯棌 WebKit 娴忚鍣ㄧ殑婊氬姩鏉?*/
.notice-tabs :deep(.ant-tabs-content-holder)::-webkit-scrollbar {
  display: none;
}

.notice-tab-pane {
  height: 100%;
}

.notice-content {
  padding: 0;
}

.markdown-content {
  line-height: 1.6;
  color: var(--ant-color-text);
}

.markdown-content :deep(h1) {
  font-size: 24px;
  font-weight: 600;
  margin: 16px 0 12px 0;
  color: var(--ant-color-text);
  border-bottom: 2px solid var(--ant-color-border);
  padding-bottom: 8px;
}

.markdown-content :deep(h2) {
  font-size: 20px;
  font-weight: 600;
  margin: 16px 0 10px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0 8px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(p) {
  margin: 8px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-content :deep(li) {
  margin: 4px 0;
  color: var(--ant-color-text);
}

.markdown-content :deep(strong) {
  font-weight: 600;
  color: var(--ant-color-text);
}

.markdown-content :deep(code) {
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 1em;
  color: var(--ant-color-primary);
  border: 1px solid var(--ant-color-border-secondary);
  font-weight: 600;
  letter-spacing: 0.5px;
}

.markdown-content :deep(pre) {
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-content :deep(pre code) {
  background: none;
  padding: 0;
  border-radius: 0;
}

.markdown-content :deep(a) {
  color: var(--ant-color-primary);
  text-decoration: none;
}

.markdown-content :deep(a:hover) {
  text-decoration: underline;
}

.markdown-content :deep(blockquote) {
  border-left: 4px solid var(--ant-color-primary);
  margin: 12px 0;
  padding: 8px 16px;
  color: var(--ant-color-text-secondary);
}

.notice-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border);
}

.notice-pagination {
  flex: 1;
}

.pagination-text {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.notice-actions {
  display: flex;
  gap: 8px;
}

.confirm-button {
  min-width: 100px;
  height: 36px;
}

/* 鍝嶅簲寮忚璁?*/
@media (max-width: 768px) {
  .notice-modal :deep(.ant-modal) {
    width: 95vw !important;
    margin: 10px;
  }

  .notice-modal :deep(.ant-modal-body) {
    padding: 12px 16px;
    max-height: 60vh;
  }

  .notice-container {
    height: 50vh;
  }

  .notice-tabs :deep(.ant-tabs-tab-list) {
    width: 120px;
  }

  .notice-tabs :deep(.ant-tabs-content-holder) {
    max-height: 40vh;
    padding-left: 8px;
  }

  .notice-footer {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .notice-actions {
    justify-content: center;
  }
}
</style>


