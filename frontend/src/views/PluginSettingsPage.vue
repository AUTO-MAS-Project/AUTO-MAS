<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons-vue'

import PluginDeclarativeForm from './plugins/components/PluginDeclarativeForm.vue'
import PageHeader from '@/components/PageHeader.vue'
import NoData from '@/components/NoData.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { usePluginQuery } from '@/views/plugins/usePluginQuery'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'
import type { DeclarativeHint } from './plugins/components/PluginDeclarativeField.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const api = usePluginApi()
const saving = ref(false)
const runningKey = ref<string | null>(null)
const title = ref('')
const pluginName = ref('')
const configUid = ref('')
const values = reactive<Record<string, Record<string, unknown>>>({})
const groups = ref<Array<{ name: string; hints: DeclarativeHint[] }>>([])

const pluginId = computed(() =>
  /* 从路由参数取得当前插件记录标识，支持同页面实例内切换插件。 */ String(
    route.params.pluginId || ''
  )
)
const errorMessage = (error: unknown) =>
  /* 从接口异常中提取可展示原因，缺失时使用插件操作失败提示。 */ apiErrorMessage(
    error,
    t('core.plugins.actionFailed')
  )

const {
  loading,
  error: loadError,
  execute: load,
} = usePluginQuery(
  () => /* 以插件身份和语言隔离配置查询缓存。 */ [
    'plugins',
    'settings',
    pluginId.value,
    locale.value,
  ],
  async () => {
    // 并发加载插件记录与专属配置，拒绝过期路由或语言结果，并建立页面标题、分组和编辑值。
    if (!pluginId.value) return null
    const requestedId = pluginId.value
    const requestedLocale = locale.value
    const [registry, config] = await Promise.all([
      api.getRegistry(pluginId.value),
      api.getConfig(pluginId.value),
    ])
    if (requestedId !== pluginId.value || requestedLocale !== locale.value) return null
    const record = (registry.data || {})[pluginId.value] as Record<string, unknown> | undefined
    const info = record?.info as Record<string, unknown> | undefined
    title.value = String(info?.display_name || info?.plugin_name || pluginId.value)
    pluginName.value = String(info?.plugin_name || '')
    for (const key of Object.keys(values)) delete values[key]
    const data =
      config.data && typeof config.data === 'object' ? (config.data as Record<string, unknown>) : {}
    configUid.value = typeof data.uid === 'string' ? data.uid : ''
    const configUi =
      data.ui && typeof data.ui === 'object' ? (data.ui as Record<string, unknown>) : {}
    const configHints =
      configUi.hints && typeof configUi.hints === 'object'
        ? (configUi.hints as Record<string, DeclarativeHint[]>)
        : {}
    // 自有配置与注册表是不同对象；插件没有自有配置时展示空态。
    const resolvedHints = configHints
    groups.value = Object.entries(resolvedHints)
      .filter(([, hints]) => hints.length > 0)
      .map(([name, hints]) => /* 将 UI 提示映射为表单分组，未提供合法提示列表时使用空列表。 */ ({
        name,
        hints: Array.isArray(hints) ? hints : [],
      }))
    for (const group of groups.value) {
      const source =
        data[group.name] && typeof data[group.name] === 'object'
          ? (data[group.name] as Record<string, unknown>)
          : {}
      values[group.name] = { ...source }
    }
    return config.data
  },
  () => /* 为插件专属配置查询提供当前语言的加载失败提示。 */ t('core.plugins.settingsLoadFailed')
)
const updateValue = (group: string, field: string, value: unknown) => {
  // 更新本地表单分组中的字段值，尚未存在的分组按需建立。
  if (!values[group]) values[group] = {}
  values[group][field] = value
}

const save = async () => {
  // 在无在途保存或动作时提交当前配置值，等待成功后重新读取后端规范化结果。
  if (saving.value || runningKey.value) return
  saving.value = true
  try {
    await api.updateConfig({ recordId: pluginId.value, data: values })
    message.success(t('core.plugins.saved'))
    await load()
  } catch (error) {
    message.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

const runAction = async (group: string, hint: DeclarativeHint, value: unknown) => {
  // 仅提交当前按钮字段的触发值，等待后台操作结果并重新加载配置，执行期间阻止重复操作。
  const field = hint.field
  if (!field || !configUid.value || hint.editable !== true || runningKey.value || saving.value)
    return
  runningKey.value = `${group}.${field}`
  try {
    if (typeof value !== 'boolean' && typeof value !== 'string') return
    const result = await api.runCommand('config', {
      configUid: configUid.value,
      group,
      field,
      value,
    })
    message.success(result.message || t('core.plugins.actionComplete'))
    await load()
  } catch (error) {
    message.error(errorMessage(error))
  } finally {
    runningKey.value = null
  }
}

watch([pluginId, locale], load, { immediate: true })
</script>

<template>
  <main class="plugin-settings-page">
    <PageHeader :title="title || t('core.plugins.settings')">
      <template #leading
        ><a-button
          type="text"
          :aria-label="t('core.plugins.back')"
          @click="router.push({ name: 'Plugins' })"
          ><ArrowLeftOutlined /></a-button
      ></template>
      <template #actions
        ><a-button
          type="primary"
          :loading="saving"
          :disabled="loading || !groups.length"
          @click="save"
          ><template #icon><SaveOutlined /></template>{{ t('core.plugins.save') }}</a-button
        ></template
      >
    </PageHeader>
    <PageSurface>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <a-spin :spinning="loading">
        <NoData
          v-if="!loading && !loadError && !groups.length"
          :description="t('core.plugins.noSettings')"
        />
        <PluginDeclarativeForm
          v-else-if="groups.length"
          :groups="groups"
          :uid="configUid"
          :namespace="`plugins.${pluginName}.config`"
          :disabled="saving || runningKey !== null"
          :values="values"
          :running-key="runningKey"
          @update:value="updateValue"
          @action="runAction"
        />
      </a-spin>
    </PageSurface>
  </main>
</template>

<style scoped>
.plugin-settings-page {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}
</style>
