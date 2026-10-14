<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons-vue'

import PluginDeclarativeForm from './plugins/components/PluginDeclarativeForm.vue'
import PageHeader from '@/components/PageHeader.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { useApiQuery } from '@/composables/useApiQuery'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'
import type { DeclarativeHint } from './plugins/components/PluginDeclarativeField.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const api = usePluginApi()
const saving = ref(false)
const runningKey = ref<string | null>(null)
const title = ref('')
const pluginName = ref('')
const values = reactive<Record<string, Record<string, unknown>>>({})
const groups = ref<Array<{ name: string; hints: DeclarativeHint[] }>>([])

const pluginId = computed(() => String(route.params.pluginId || ''))
const errorMessage = (error: unknown) => apiErrorMessage(error, t('plugins.actionFailed'))

const {
  loading,
  error: loadError,
  execute: load,
} = useApiQuery(
  async () => {
    if (!pluginId.value) return
    const [registry, config] = await Promise.all([
      api.getRegistry(pluginId.value),
      api.getConfig(pluginId.value),
    ])
    const record = (registry.data || {})[pluginId.value] as Record<string, unknown> | undefined
    const info = record?.info as Record<string, unknown> | undefined
    title.value = String(info?.display_name || info?.plugin_name || pluginId.value)
    pluginName.value = String(info?.plugin_name || '')
    for (const key of Object.keys(values)) delete values[key]
    const data =
      config.data && typeof config.data === 'object' ? (config.data as Record<string, unknown>) : {}
    const configUi =
      data.ui && typeof data.ui === 'object' ? (data.ui as Record<string, unknown>) : {}
    const configHints =
      configUi.hints && typeof configUi.hints === 'object'
        ? (configUi.hints as Record<string, DeclarativeHint[]>)
        : {}
    // 自有配置与注册表是不同对象；插件没有自有配置时展示空态。
    const resolvedHints = configHints
    groups.value = Object.entries(resolvedHints).map(([name, hints]) => ({
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
  },
  () => t('plugins.settingsLoadFailed')
)
const updateValue = (group: string, field: string, value: unknown) => {
  if (!values[group]) values[group] = {}
  values[group][field] = value
}

const save = async () => {
  if (saving.value || runningKey.value) return
  saving.value = true
  try {
    await api.updateConfig({ recordId: pluginId.value, data: values })
    message.success(t('plugins.saved'))
    await load()
  } catch (error) {
    message.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

const runAction = async (group: string, hint: DeclarativeHint, value: unknown) => {
  const field = hint.field
  if (!field || runningKey.value || saving.value) return
  runningKey.value = `${group}.${field}`
  try {
    const result = await api.updateConfig({
      recordId: pluginId.value,
      data: { [group]: { [field]: value } },
    })
    message.success(result.message || t('plugins.actionComplete'))
    await load()
  } catch (error) {
    message.error(errorMessage(error))
  } finally {
    runningKey.value = null
  }
}

watch(pluginId, load, { immediate: true })
</script>

<template>
  <main class="plugin-settings-page">
    <PageHeader :title="title || t('plugins.settings')">
      <template #leading
        ><a-button
          type="text"
          :aria-label="t('plugins.back')"
          @click="router.push({ name: 'Plugins' })"
          ><ArrowLeftOutlined /></a-button
      ></template>
      <template #actions
        ><a-button
          type="primary"
          :loading="saving"
          :disabled="loading || !groups.length"
          @click="save"
          ><template #icon><SaveOutlined /></template>{{ t('plugins.save') }}</a-button
        ></template
      >
    </PageHeader>
    <PageSurface>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <a-spin :spinning="loading">
        <a-empty v-if="!loading && !groups.length" :description="t('plugins.noSettings')" />
        <PluginDeclarativeForm
          v-else
          :groups="groups"
          :uid="pluginId"
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
