<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { AppstoreOutlined, MoreOutlined, ReloadOutlined, SettingOutlined, ShopOutlined } from '@ant-design/icons-vue'
import type { PluginRecord } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { useApiQuery } from '@/composables/useApiQuery'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'

type PluginRow = { uid: string; info: Record<string, unknown>; ui: Record<string, unknown> }
const { t } = useI18n()
const api = usePluginApi()
const rows = ref<PluginRow[]>([])
const expandedRowKeys = ref<string[]>([])
const running = ref(false)

const normalize = (uid: string, value: PluginRecord): PluginRow => {
  const source = value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
  return { uid, info: source.info && typeof source.info === 'object' ? source.info as Record<string, unknown> : {}, ui: source.ui && typeof source.ui === 'object' ? source.ui as Record<string, unknown> : {} }
}
const pluginName = (row: PluginRow) => String(row.info.display_name || row.info.plugin_name || row.uid)
const status = (row: PluginRow) => String(row.info.state || 'unloaded')
const tags = (row: PluginRow) => Array.isArray(row.info.tags) ? row.info.tags : []
const listValue = (value: unknown) => Array.isArray(value) ? value.join(', ') : String(value || '-')
const textValue = (value: unknown) => value === undefined || value === null || value === '' ? '-' : String(value)
const flagValue = (value: unknown) => value === true ? t('common.yes') : value === false ? t('common.no') : '-'
const statusColor = (value: string) => value === 'enabled' ? 'success' : value.startsWith('fault') ? 'error' : ['disabled', 'unloaded'].includes(value) ? 'default' : 'processing'

const { loading, error: loadError, execute: load } = useApiQuery(async () => {
  const result = await api.getRegistry()
  const data = result.data || {}
  rows.value = (result.order || []).map(item => normalize(item.uid, data[item.uid] || {}))
}, () => t('plugins.loadFailed'))
const trigger = async (row: PluginRow, action: 'enable' | 'disable' | 'reload' | 'uninstall') => {
  if (running.value) return
  running.value = true
  try {
    const result = await api.updateRegistry({ recordId: row.uid, data: { info: { [action]: true } } })
    message.success(result.message || t('plugins.actionComplete'))
    await load()
  } catch (error) { message.error(apiErrorMessage(error, t('plugins.actionFailed'))) }
  finally { running.value = false }
}
const toggleExpanded = (uid: string) => { expandedRowKeys.value = expandedRowKeys.value.includes(uid) ? expandedRowKeys.value.filter(key => key !== uid) : [...expandedRowKeys.value, uid] }
const handleExpand = (expanded: boolean, row: PluginRow) => {
  expandedRowKeys.value = expanded
    ? expandedRowKeys.value.includes(row.uid) ? expandedRowKeys.value : [...expandedRowKeys.value, row.uid]
    : expandedRowKeys.value.filter(key => key !== row.uid)
}
onMounted(load)
</script>

<template>
  <main class="plugins-page">
    <PageHeader :title="t('plugins.title')" :icon="AppstoreOutlined">
      <template #actions>
        <a-button :loading="loading" @click="load"><template #icon><ReloadOutlined /></template>{{ t('plugins.refresh') }}</a-button>
        <a-button type="primary" @click="$router.push({ name: 'PluginMarket' })"><template #icon><ShopOutlined /></template>{{ t('plugins.marketButton') }}</a-button>
      </template>
    </PageHeader>
    <PageSurface>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <a-table :data-source="rows" :loading="loading" row-key="uid" :pagination="false" :expanded-row-keys="expandedRowKeys" :locale="{ emptyText: t('plugins.empty') }" @expand="handleExpand">
        <a-table-column key="name" :title="t('plugins.attribute.name')" :width="240">
          <template #default="{ record }"><div class="plugin-name-cell"><a class="plugin-name" @click="toggleExpanded(record.uid)">{{ pluginName(record) }}</a><span class="plugin-id">{{ record.info.package_name || record.uid }}</span><span class="plugin-description">{{ record.info.description || t('plugins.noDescription') }}</span></div></template>
        </a-table-column>
        <a-table-column key="tags" :title="t('plugins.tags')" :width="180"><template #default="{ record }"><a-space wrap size="small"><a-tag v-for="tag in tags(record)" :key="String(tag)">{{ tag }}</a-tag><span v-if="!tags(record).length" class="muted">-</span></a-space></template></a-table-column>
        <a-table-column key="state" :title="t('plugins.attribute.status')" :width="120"><template #default="{ record }"><a-tag :color="statusColor(status(record))">{{ status(record) }}</a-tag></template></a-table-column>
        <a-table-column key="version" :title="t('plugins.attribute.version')" :width="120"><template #default="{ record }">{{ record.info.version || '-' }}</template></a-table-column>
        <a-table-column key="source" :title="t('plugins.attribute.source')" :width="120"><template #default="{ record }">{{ record.info.source || '-' }}</template></a-table-column>
        <a-table-column key="error" :title="t('plugins.attribute.error')"><template #default="{ record }"><span v-if="record.info.last_error" class="error-text">{{ record.info.last_error }}</span><span v-else class="muted">-</span></template></a-table-column>
        <a-table-column key="actions" :title="t('plugins.action')" :width="116" align="right" fixed="right">
          <template #default="{ record }"><a-space size="small"><a-button type="text" :aria-label="t('plugins.settings')" @click="$router.push({ name: 'PluginSettings', params: { pluginId: record.uid } })"><SettingOutlined /></a-button><a-dropdown placement="bottomRight"><a-button type="text" :disabled="running" :aria-label="t('plugins.moreActions')"><MoreOutlined /></a-button><template #overlay><a-menu><a-menu-item key="enable" :disabled="status(record) === 'enabled'" @click="trigger(record, 'enable')">{{ t('plugins.enable') }}</a-menu-item><a-menu-item key="disable" :disabled="status(record) !== 'enabled'" @click="trigger(record, 'disable')">{{ t('plugins.disable') }}</a-menu-item><a-menu-item key="reload" @click="trigger(record, 'reload')">{{ t('plugins.reload') }}</a-menu-item><a-menu-divider /><a-menu-item key="uninstall" danger @click="trigger(record, 'uninstall')">{{ t('plugins.uninstall') }}</a-menu-item></a-menu></template></a-dropdown></a-space></template>
        </a-table-column>
        <template #expandedRowRender="{ record }"><a-descriptions class="plugin-details" size="small" :column="3" bordered><a-descriptions-item :label="t('plugins.attribute.author')">{{ textValue(record.info.author) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.license')">{{ textValue(record.info.license) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.requiresDist')">{{ listValue(record.info.requires_dist) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.importName')">{{ textValue(record.info.import_name) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.repository')">{{ textValue(record.info.repository) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.homepage')">{{ textValue(record.info.homepage) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.docs')">{{ textValue(record.info.docs_url) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.requires')">{{ listValue(record.info.requires) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.wants')">{{ listValue(record.info.wants) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.lifecycle')">{{ textValue(record.info.lifecycle_context) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.enabled')">{{ flagValue(record.info.enabled) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.core')">{{ flagValue(record.info.is_core) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.local')">{{ flagValue(record.info.is_local) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.codeDrift')">{{ textValue(record.info.code_drift) }}</a-descriptions-item><a-descriptions-item :label="t('plugins.attribute.error')">{{ textValue(record.info.last_error) }}</a-descriptions-item></a-descriptions></template>
      </a-table>
    </PageSurface>
  </main>
</template>

<style scoped>
.plugins-page { display: flex; height: 100%; min-height: 0; flex-direction: column; overflow: hidden; }
.plugin-name-cell { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.plugin-name { overflow: hidden; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.plugin-id, .plugin-description, .muted { color: var(--ant-color-text-tertiary); font-size: 12px; }
.plugin-description { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.error-text { color: var(--ant-color-error); }
.plugin-details { margin: 0 8px; }
</style>
