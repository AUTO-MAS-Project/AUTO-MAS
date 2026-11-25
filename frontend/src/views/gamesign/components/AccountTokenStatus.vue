<!--
  凭据体检与自动续期。
  插件下线时（404 / 400「未启用」）整块隐藏：这时候任何按钮都点不出结果，
  摆在界面上只会让人以为功能坏了。
-->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { StatusChip } from '@/components/ui'
import { SignflowError, signflowApi, type SignflowTokenItem } from '@/services/signflowApi'

const props = defineProps<{
  accountUid: string
  /** 抽屉每次打开递增：切换账号后旧结果不能再写回来 */
  session: number
}>()

const emit = defineEmits<{ refreshed: [field: string] }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('游戏社区')

const items = ref<SignflowTokenItem[]>([])
const loading = ref(false)
const refreshing = ref(false)
const errorMessage = ref('')
/** 插件未启用/未解锁时整块不显示 */
const unavailable = ref(false)

const isPluginUnavailable = (error: unknown): boolean =>
  error instanceof SignflowError &&
  (error.code === 404 || (error.code === 400 && error.message.includes('未启用')))

const loadStatus = async () => {
  if (!props.accountUid) return
  const session = props.session
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await signflowApi.tokenStatus([props.accountUid])
    if (session !== props.session) return
    const account = result.data.find(entry => entry.uid === props.accountUid)
    items.value = account?.items ?? []
    unavailable.value = false
  } catch (error) {
    if (session !== props.session) return
    if (isPluginUnavailable(error)) {
      unavailable.value = true
      items.value = []
      return
    }
    logger.error(`读取凭据状态失败: ${error instanceof Error ? error.message : String(error)}`)
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    if (session === props.session) loading.value = false
  }
}

const refreshable = computed(() => items.value.filter(item => item.configured))

const toneOf = (item: SignflowTokenItem): 'success' | 'warning' | 'neutral' => {
  if (!item.configured) return 'neutral'
  if (!item.checked) return 'neutral'
  return item.valid ? 'success' : 'warning'
}

const refresh = async () => {
  if (!props.accountUid) return
  const session = props.session
  refreshing.value = true
  try {
    const result = await signflowApi.refreshToken(props.accountUid)
    if (session !== props.session) return
    const failed = result.items.filter(item => !item.refreshed)
    if (failed.length) {
      message.warning(
        t('core.gamesign.token.refreshPartial', {
          items: failed.map(item => item.message).join('；'),
        })
      )
    } else {
      message.success(t('core.gamesign.token.refreshDone'))
    }
    // 刷新成功的字段由后端直接写库，通知抽屉回读该字段
    for (const item of result.items) {
      if (item.refreshed) emit('refreshed', item.field)
    }
    await loadStatus()
  } catch (error) {
    if (session !== props.session) return
    if (isPluginUnavailable(error)) {
      unavailable.value = true
      return
    }
    message.error(error instanceof Error ? error.message : String(error))
  } finally {
    if (session === props.session) refreshing.value = false
  }
}

watch(
  () => [props.accountUid, props.session] as const,
  () => {
    items.value = []
    errorMessage.value = ''
    void loadStatus()
  },
  { immediate: true }
)
</script>

<template>
  <section v-if="!unavailable" class="token-block">
    <div class="token-head">
      <span class="token-title">{{ t('core.gamesign.token.title') }}</span>
      <a-button
        v-if="refreshable.length"
        type="link"
        size="small"
        :loading="refreshing"
        @click="refresh"
      >
        <template #icon><ReloadOutlined /></template>
        {{ t('core.gamesign.token.refresh') }}
      </a-button>
    </div>
    <div v-if="items.length" class="token-list">
      <div v-for="item in items" :key="item.field" class="token-row">
        <span class="token-platform">{{ item.platform }}</span>
        <span class="token-message">{{ item.message }}</span>
        <StatusChip :tone="toneOf(item)">
          {{ item.valid ? t('core.gamesign.token.valid') : t('core.gamesign.token.invalid') }}
        </StatusChip>
      </div>
    </div>
    <p v-else-if="!loading && !errorMessage" class="token-empty">
      {{ t('core.gamesign.token.empty') }}
    </p>
    <a-alert v-if="errorMessage" type="error" show-icon :message="errorMessage" />
  </section>
</template>

<style scoped>
.token-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.token-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.token-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.token-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.token-row {
  display: grid;
  grid-template-columns: minmax(64px, auto) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.token-platform {
  font-size: 13px;
  color: var(--ant-color-text);
}

.token-message {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.token-empty {
  margin: 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
