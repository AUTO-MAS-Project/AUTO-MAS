<script setup lang="ts">
import { computed, onUnmounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CodeOutlined, SelectOutlined, DesktopOutlined, BulbOutlined } from '@ant-design/icons-vue'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { queryClient } from '@/services/queryClient'
import { openVueDevtools } from './vueDevtools'

const emit = defineEmits<{ inspect: [] }>()
const { t } = useI18n()
const { themeMode, setThemeMode } = useTheme()
const busy = ref('')
const queries = shallowRef(queryClient.getQueryCache().getAll())
const stopCache = queryClient.getQueryCache().subscribe(() => {
  queries.value = [...queryClient.getQueryCache().getAll()]
})
onUnmounted(stopCache)
const cacheSummary = computed(() => ({
  total: queries.value.length,
  fetching: queries.value.filter(query => query.state.fetchStatus === 'fetching').length,
  failed: queries.value.filter(query => query.state.status === 'error').length,
}))
const themeOptions = computed(() => [
  { label: t('devtools.light'), value: 'light' },
  { label: t('devtools.dark'), value: 'dark' },
  { label: t('devtools.system'), value: 'system' },
])

const launchVue = async (inspect: boolean) => {
  if (busy.value) return
  busy.value = inspect ? 'inspector' : 'vue'
  try {
    if (await openVueDevtools(inspect)) emit('inspect')
    else message.error(t('devtools.vueUnavailable'))
  } catch {
    message.error(t('devtools.vueUnavailable'))
  } finally {
    busy.value = ''
  }
}

const openChromium = async () => {
  if (!window.electronAPI?.openDevTools) {
    message.info(t('devtools.browserDevtoolsHint'))
    return
  }
  try {
    await window.electronAPI.openDevTools()
  } catch {
    message.error(t('devtools.nativeDevtoolsFailed'))
  }
}

const changeTheme = async (value: string | number) => {
  if (busy.value) return
  busy.value = 'theme'
  try {
    await setThemeMode(value as ThemeMode)
  } catch {
    message.error(t('devtools.themeFailed'))
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <section class="devtools-section">
    <h3><CodeOutlined /> Vue DevTools</h3>
    <p class="devtools-muted">{{ t('devtools.vueHint') }}</p>
    <a-space wrap>
      <a-button
        type="primary"
        :loading="busy === 'vue'"
        :disabled="!!busy && busy !== 'vue'"
        @click="launchVue(false)"
        ><CodeOutlined />{{ t('devtools.openVue') }}</a-button
      >
      <a-button
        :loading="busy === 'inspector'"
        :disabled="!!busy && busy !== 'inspector'"
        @click="launchVue(true)"
        ><SelectOutlined />{{ t('devtools.inspectComponent') }}</a-button
      >
    </a-space>
    <p class="tool-shortcut devtools-muted">{{ t('devtools.vueShortcut') }}</p>
  </section>
  <section class="devtools-section">
    <h3><DesktopOutlined /> {{ t('devtools.chromiumTools') }}</h3>
    <p class="devtools-muted">{{ t('devtools.chromiumHint') }}</p>
    <a-button @click="openChromium">{{ t('devtools.openChromium') }}</a-button>
  </section>
  <section class="devtools-section">
    <h3><BulbOutlined /> {{ t('devtools.themeCheck') }}</h3>
    <p class="devtools-muted">{{ t('devtools.themeHint') }}</p>
    <a-segmented
      :value="themeMode"
      :options="themeOptions"
      :disabled="!!busy"
      @change="changeTheme"
    />
  </section>
  <section class="devtools-section">
    <h3>{{ t('devtools.queryCache') }}</h3>
    <a-descriptions :column="3" size="small">
      <a-descriptions-item :label="t('devtools.cacheTotal')">{{
        cacheSummary.total
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('devtools.cacheFetching')">{{
        cacheSummary.fetching
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('devtools.cacheFailed')">{{
        cacheSummary.failed
      }}</a-descriptions-item>
    </a-descriptions>
    <p class="devtools-muted">{{ t('devtools.cacheHint') }}</p>
  </section>
</template>

<style scoped>
.tool-shortcut {
  margin: 12px 0 0;
}
</style>
