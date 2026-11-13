<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'

import { useRouter } from 'vue-router'
import type { PluginConfigUi } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import NoData from '@/components/NoData.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { usePluginQuery } from '@/views/plugins/usePluginQuery'
import { usePluginApi } from '@/composables/usePluginApi'
import { pluginActionHint } from '@/views/plugins/configActions'
import { apiErrorMessage } from '@/utils/apiResult'

type CatalogRow = { uid: string; info: Record<string, unknown>; ui?: PluginConfigUi }
const { t, locale } = useI18n()
const router = useRouter()
const api = usePluginApi()
const refreshing = ref(false)
const installing = ref<string | null>(null)

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
  async () => {
    // 请求市场目录并转换为带唯一标识的列表行，兼容配置投影中的 info 分组。
    const result = await api.getCatalog()
    return Object.entries(result.data || {}).map(
      ([uid, value]) => /* 将一个市场配置条目展开为页面使用的标识和信息对象。 */ ({
        uid,
        ui: value.ui,
        info:
          value && typeof value === 'object' && 'info' in value
            ? ((value as Record<string, unknown>).info as Record<string, unknown>)
            : (value as Record<string, unknown>),
      })
    )
  },
  () => /* 为市场查询提供当前语言的加载失败提示。 */ t('core.plugins.marketLoadFailed')
)

const rows = computed(() => /* 读取市场查询结果，尚无数据时提供空列表。 */ queryRows.value ?? [])

const refresh = async () => {
  // 互斥执行市场刷新，重新加载目录并显示成功或失败结果，结束时释放刷新状态。
  refreshing.value = true
  try {
    await api.refreshCatalog()
    await load()
    message.success(t('core.plugins.marketRefreshed'))
  } catch (error) {
    message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
  } finally {
    refreshing.value = false
  }
}

const install = async (row: CatalogRow) => {
  // 提交选中市场条目的安装触发器，等待结果后反馈并刷新安装状态。
  if (installing.value || pluginActionHint(row.ui, 'info', 'install')?.editable !== true) return
  installing.value = row.uid
  try {
    await api.runCommand('install', {
      configUid: row.uid,
      group: 'info',
      field: 'install',
      value: true,
    })
    await load()
    message.success(t('core.plugins.installed'))
  } catch (error) {
    message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
  } finally {
    installing.value = null
  }
}

watch(locale, load, { immediate: true })
</script>

<template>
  <main class="plugins-page">
    <PageHeader :title="t('core.plugins.marketTitle')">
      <template #actions
        ><a-button
          type="text"
          :aria-label="t('core.plugins.back')"
          @click="router.push({ name: 'Plugins' })"
          ><ArrowLeftOutlined /></a-button
        ><a-button :loading="refreshing" @click="refresh"
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
          ><template #default="{ record }">{{
            record.info.version || '-'
          }}</template></a-table-column
        >
        <a-table-column key="source" :title="t('core.plugins.attribute.source')"
          ><template #default="{ record }">{{
            record.info.package_name || '-'
          }}</template></a-table-column
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
              >{{ t('core.plugins.install') }}</a-button
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
