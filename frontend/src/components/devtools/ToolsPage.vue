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
  { label: t('core.devtools.light'), value: 'light' },
  { label: t('core.devtools.dark'), value: 'dark' },
  { label: t('core.devtools.system'), value: 'system' },
])

const launchVue = async (inspect: boolean) => {
  if (busy.value) return
  busy.value = inspect ? 'inspector' : 'vue'
  try {
    if (await openVueDevtools(inspect)) emit('inspect')
    else message.error(t('core.devtools.vueUnavailable'))
  } catch {
    message.error(t('core.devtools.vueUnavailable'))
  } finally {
    busy.value = ''
  }
}

const openChromium = async () => {
  if (!window.electronAPI?.openDevTools) {
    message.info(t('core.devtools.browserDevtoolsHint'))
    return
  }
  try {
    await window.electronAPI.openDevTools()
  } catch {
    message.error(t('core.devtools.nativeDevtoolsFailed'))
  }
}

const changeTheme = async (value: string | number) => {
  if (busy.value) return
  busy.value = 'theme'
  try {
    await setThemeMode(value as ThemeMode)
  } catch {
    message.error(t('core.devtools.themeFailed'))
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <section class="devtools-section">
    <h3><CodeOutlined /> Vue DevTools</h3>
    <p class="devtools-muted">{{ t('core.devtools.vueHint') }}</p>
    <a-space wrap>
      <a-button
        type="primary"
        :loading="busy === 'vue'"
        :disabled="!!busy && busy !== 'vue'"
        @click="launchVue(false)"
        ><CodeOutlined />{{ t('core.devtools.openVue') }}</a-button
      >
      <a-button
        :loading="busy === 'inspector'"
        :disabled="!!busy && busy !== 'inspector'"
        @click="launchVue(true)"
        ><SelectOutlined />{{ t('core.devtools.inspectComponent') }}</a-button
      >
    </a-space>
    <p class="tool-shortcut devtools-muted">{{ t('core.devtools.vueShortcut') }}</p>
  </section>
  <section class="devtools-section">
    <h3><DesktopOutlined /> {{ t('core.devtools.chromiumTools') }}</h3>
    <p class="devtools-muted">{{ t('core.devtools.chromiumHint') }}</p>
    <a-button @click="openChromium">{{ t('core.devtools.openChromium') }}</a-button>
  </section>
  <section class="devtools-section">
    <h3><BulbOutlined /> {{ t('core.devtools.themeCheck') }}</h3>
    <p class="devtools-muted">{{ t('core.devtools.themeHint') }}</p>
    <a-segmented
      :value="themeMode"
      :options="themeOptions"
      :disabled="!!busy"
      @change="changeTheme"
    />
  </section>
  <section class="devtools-section">
    <h3>{{ t('core.devtools.queryCache') }}</h3>
    <a-descriptions :column="3" size="small">
      <a-descriptions-item :label="t('core.devtools.cacheTotal')">{{
        cacheSummary.total
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.cacheFetching')">{{
        cacheSummary.fetching
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.cacheFailed')">{{
        cacheSummary.failed
      }}</a-descriptions-item>
    </a-descriptions>
    <p class="devtools-muted">{{ t('core.devtools.cacheHint') }}</p>
  </section>
</template>

<style scoped>
.tool-shortcut {
  margin: 12px 0 0;
}
</style>
