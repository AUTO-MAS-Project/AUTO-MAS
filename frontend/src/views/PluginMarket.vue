<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'

import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { useApiQuery } from '@/composables/useApiQuery'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'

type CatalogRow = { uid: string; info: Record<string, unknown> }
const { t } = useI18n()
const router = useRouter()
const api = usePluginApi()
const refreshing = ref(false)
const installing = ref<string | null>(null)
const rows = ref<CatalogRow[]>([])

const {
  loading,
  error: loadError,
  execute: load,
} = useApiQuery(
  async () => {
    const result = await api.getCatalog()
    rows.value = Object.entries(result.data || {}).map(([uid, value]) => ({
      uid,
      info:
        value && typeof value === 'object' && 'info' in value
          ? ((value as Record<string, unknown>).info as Record<string, unknown>)
          : (value as Record<string, unknown>),
    }))
  },
  () => t('plugins.marketLoadFailed')
)

const refresh = async () => {
  refreshing.value = true
  try {
    await api.refreshCatalog()
    await load()
    message.success(t('plugins.marketRefreshed'))
  } catch (error) {
    message.error(apiErrorMessage(error, t('plugins.actionFailed')))
  } finally {
    refreshing.value = false
  }
}

const install = async (row: CatalogRow) => {
  if (installing.value) return
  installing.value = row.uid
  try {
    await api.updateCatalog({
      metaId: row.uid,
      data: { info: { install: true } },
    })
    message.success(t('plugins.installed'))
  } catch (error) {
    message.error(apiErrorMessage(error, t('plugins.actionFailed')))
  } finally {
    installing.value = null
  }
}

onMounted(load)
</script>

<template>
  <main class="plugins-page">
    <PageHeader :title="t('plugins.marketTitle')">
      <template #leading
        ><a-button
          type="text"
          :aria-label="t('plugins.back')"
          @click="router.push({ name: 'Plugins' })"
          ><ArrowLeftOutlined /></a-button
      ></template>
      <template #actions
        ><a-button :loading="refreshing" @click="refresh"
          ><template #icon><ReloadOutlined /></template>{{ t('plugins.refresh') }}</a-button
        ></template
      >
    </PageHeader>
    <PageSurface>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <a-table :data-source="rows" :loading="loading" row-key="uid" :pagination="false">
        <a-table-column key="name" :title="t('plugins.attribute.name')"
          ><template #default="{ record }">{{
            record.info.display_name || record.info.plugin_name || record.uid
          }}</template></a-table-column
        >
        <a-table-column key="description" :title="t('plugins.attribute.description')"
          ><template #default="{ record }">{{
            record.info.description || t('plugins.noDescription')
          }}</template></a-table-column
        >
        <a-table-column key="version" :title="t('plugins.attribute.version')"
          ><template #default="{ record }">{{
            record.info.version || '-'
          }}</template></a-table-column
        >
        <a-table-column key="source" :title="t('plugins.attribute.source')"
          ><template #default="{ record }">{{
            record.info.package_name || '-'
          }}</template></a-table-column
        >
        <a-table-column key="action" :title="t('plugins.action')" align="right"
          ><template #default="{ record }"
            ><a-button
              type="primary"
              size="small"
              :loading="installing === record.uid"
              :disabled="installing !== null"
              @click="install(record)"
              ><template #icon><DownloadOutlined /></template>{{ t('plugins.install') }}</a-button
            ></template
          ></a-table-column
        >
      </a-table>
      <a-empty
        v-if="!loading && !loadError && !rows.length"
        :description="t('plugins.marketEmpty')"
      />
    </PageSurface>
  </main>
</template>

<style scoped>
.plugins-page {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}
</style>
