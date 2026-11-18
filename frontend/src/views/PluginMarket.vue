<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'

import { useRouter } from 'vue-router'
import type { PluginCatalogDocument } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import NoData from '@/components/NoData.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { usePluginQuery } from '@/views/plugins/usePluginQuery'
import { usePluginApi } from '@/composables/usePluginApi'
import { usePluginInstallation } from '@/views/plugins/usePluginInstallation'
import { pluginActionHint } from '@/views/plugins/configActions'
import { apiErrorMessage } from '@/utils/apiResult'
import PluginMetadataDetails from '@/views/plugins/PluginMetadataDetails.vue'

const { t, locale } = useI18n()
const router = useRouter()
const api = usePluginApi()
const refreshing = ref(false)
const {
  installing,
  install: installPlugin,
  messageHolder: installationMessageHolder,
} = usePluginInstallation()

const {
  data: queryRows,
  loading,
  error: loadError,
  execute: load,
} = usePluginQuery(
  () => /* 以当前语言隔离市场查询缓存，切换语言时取得对应展示文本。 */ [
    'plugins',
    'market',
    locale.value,
  ],
  api.getCatalog,
  () => /* 为市场查询提供当前语言的加载失败提示。 */ t('core.plugins.marketLoadFailed')
)

const rows = computed(() =>
  /* 读取市场查询结果，尚无数据时提供空列表。 */ Object.values(queryRows.value?.data ?? {}).map(
    row => ({ ...row, info: row.info ?? {} })
  )
)

const refresh = async () => {
  // 互斥执行市场刷新，重新加载目录并显示成功或失败结果，结束时释放刷新状态。
  refreshing.value = true
  try {
    await api.refreshCatalog()
    if (await load()) message.success(t('core.plugins.marketRefreshed'))
  } catch (error) {
    message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
  } finally {
    refreshing.value = false
  }
}

const install = async (row: PluginCatalogDocument) => {
  // 更新完成后重新读取安装版本及操作权限。
  if (await installPlugin(row)) await load()
}

watch(locale, load, { immediate: true })
</script>

<template>
  <main class="plugins-page">
    <installation-message-holder />
    <PageHeader :title="t('core.plugins.marketTitle')">
      <template #actions
        ><a-button
          type="text"
          :aria-label="t('core.plugins.back')"
          @click="router.push({ name: 'Plugins' })"
          ><ArrowLeftOutlined /></a-button
        ><a-button :loading="refreshing || loading" :disabled="installing !== null" @click="refresh"
          ><template #icon><ReloadOutlined /></template>{{ t('core.plugins.refresh') }}</a-button
        ></template
      >
    </PageHeader>
    <PageSurface>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <a-table
        v-if="rows.length || loading"
        :data-source="rows"
        :loading="loading"
        row-key="uid"
        :pagination="false"
      >
        <template #emptyText><span /></template>
        <template #expandedRowRender="{ record }">
          <PluginMetadataDetails :info="record.info" />
        </template>
        <a-table-column key="name" :title="t('core.plugins.attribute.name')"
          ><template #default="{ record }">{{
            record.info.display_name || record.info.plugin_name || record.uid
          }}</template></a-table-column
        >
        <a-table-column key="description" :title="t('core.plugins.attribute.description')"
          ><template #default="{ record }">{{
            record.info.description || t('core.plugins.noDescription')
          }}</template></a-table-column
        >
        <a-table-column key="version" :title="t('core.plugins.attribute.version')"
          ><template #default="{ record }"
            >{{ record.info.version || '-' }}
            <div v-if="record.info.installed_version">
              <a-typography-text type="secondary">{{
                t('core.plugins.installedVersion', { version: record.info.installed_version })
              }}</a-typography-text>
            </div></template
          ></a-table-column
        >
        <a-table-column key="tags" :title="t('core.plugins.tags')"
          ><template #default="{ record }">
            <a-space wrap size="small">
              <a-tag v-for="tag in record.info.tags || []" :key="tag">{{ tag }}</a-tag>
              <span v-if="!record.info.tags?.length">-</span>
            </a-space>
          </template></a-table-column
        >
        <a-table-column key="action" :title="t('core.plugins.action')" align="right"
          ><template #default="{ record }"
            ><a-button
              v-if="pluginActionHint(record.ui, 'info', 'install')"
              type="primary"
              size="small"
              :loading="installing === record.uid"
              :disabled="
                installing !== null ||
                pluginActionHint(record.ui, 'info', 'install')?.editable !== true
              "
              @click="install(record)"
              ><template #icon><DownloadOutlined /></template
              >{{
                t(
                  record.info.update_available
                    ? 'core.plugins.upgrade'
                    : record.info.installed_version
                      ? 'core.plugins.alreadyInstalled'
                      : 'core.plugins.install'
                )
              }}</a-button
            ></template
          ></a-table-column
        >
      </a-table>
      <NoData
        v-if="!loading && !loadError && !rows.length"
        :description="t('core.plugins.marketEmpty')"
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
