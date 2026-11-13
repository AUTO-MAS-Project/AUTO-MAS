<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { MoreOutlined, ReloadOutlined, SettingOutlined, ShopOutlined } from '@ant-design/icons-vue'
import type { PluginRegistryDocument, PluginConfigUi } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import NoData from '@/components/NoData.vue'
import { usePluginQuery } from '@/views/plugins/usePluginQuery'
import { usePluginApi } from '@/composables/usePluginApi'
import { pluginActionHint, pluginToggleChecked } from '@/views/plugins/configActions'
import { apiErrorMessage } from '@/utils/apiResult'

type PluginRow = {
  uid: string
  info: Record<string, unknown>
  ui?: PluginConfigUi
  disableImpact: PluginRegistryDocument['disableImpact']
}
const { t, te, locale } = useI18n()
const api = usePluginApi()
const expandedRowKeys = ref<string[]>([])
const running = ref(false)

const normalize = (uid: string, value?: PluginRegistryDocument): PluginRow => {
  // 保留后端配置字段和 UI 属性，不再以运行状态推断操作权限。
  return { uid, info: value?.info ?? {}, ui: value?.ui, disableImpact: value?.disableImpact ?? [] }
}
const pluginText = (row: PluginRow, field: string, fallback: string) => {
  // 优先读取插件资源命名空间中的展示文本，缺失时使用注册记录中的回退文本。
  const key = `plugins.${row.info.plugin_name}.${field}`
  return te(key) ? t(key) : fallback
}
const pluginName = (row: PluginRow) =>
  /* 取得插件当前语言的展示名称，依次回退到记录名称、插件名或标识。 */ pluginText(
    row,
    'display_name',
    String(row.info.display_name || row.info.plugin_name || row.uid)
  )
const status = (row: PluginRow) =>
  /* 读取插件运行状态，尚未加载时使用 unloaded 展示状态。 */ String(row.info.state || 'unloaded')
const tags = (row: PluginRow) => {
  // 优先读取插件多语言标签，格式无效或缺失时使用记录中的标签列表。
  const key = `plugins.${row.info.plugin_name}.tags`
  if (te(key)) {
    try {
      const value: unknown = JSON.parse(t(key))
      if (Array.isArray(value))
        return value.filter(
          item =>
            /* 仅保留插件标签资源中的文本项，避免无效值进入标签组件。 */ typeof item === 'string'
        )
    } catch {
      /* 缺失或不合法的词条回退到注册信息。 */
    }
  }
  return Array.isArray(row.info.tags) ? row.info.tags : []
}
const enumText = (kind: string, value: unknown) => {
  // 将运行状态等枚举转换为当前语言文本，无词条时展示原值或占位。
  const key = `core.plugins.${kind}.${value}`
  const text = t(key)
  return text === key ? String(value || '-') : text
}
const listValue = (value: unknown) =>
  /* 将依赖等列表转换为逗号分隔文本，空值使用占位。 */ Array.isArray(value)
    ? value.join(', ')
    : String(value || '-')
const textValue = (value: unknown) =>
  /* 将详情字段转换为展示文本，对空值统一显示占位。 */ value === undefined ||
  value === null ||
  value === ''
    ? '-'
    : String(value)
const flagValue = (value: unknown) =>
  /* 将布尔详情字段转换为当前语言的是或否，未知值显示占位。 */ value === true
    ? t('core.common.yes')
    : value === false
      ? t('core.common.no')
      : '-'
const statusColor = (value: string) =>
  /* 将启用、故障、停用和处理中状态映射为页面状态标签颜色。 */ value === 'enabled'
    ? 'success'
    : value.startsWith('fault')
      ? 'error'
      : ['disabled', 'unloaded'].includes(value)
        ? 'default'
        : 'processing'

const {
  data: queryRows,
  loading,
  error: loadError,
  execute: load,
} = usePluginQuery(
  () => /* 以当前语言区分已安装插件列表的查询缓存。 */ ['plugins', 'installed', locale.value],
  async () => {
    // 注册配置已包含运行状态及 UI 属性，直接使用这一份权威数据。
    const result = await api.getRegistry()
    return (result.order ?? []).map(item => normalize(item.uid, result.data?.[item.uid]))
  },
  () => /* 为插件列表查询提供当前语言的加载失败提示。 */ t('core.plugins.loadFailed')
)
const rows = computed(
  () => /* 读取注册配置中的插件行，尚无查询结果时返回空列表。 */ queryRows.value ?? []
)

const trigger = async (row: PluginRow, action: 'enable' | 'disable' | 'reload' | 'uninstall') => {
  // 互斥提交插件启用、停用、重载或卸载触发器，等待后台结果后提示并刷新列表。
  if (running.value || pluginActionHint(row.ui, 'info', action)?.editable !== true) return
  running.value = true
  try {
    if (action === 'disable' && row.disableImpact?.length) {
      const confirmed = await new Promise<boolean>(resolve => {
        // 适配器及级联下游停用会删除配置；在提交触发器前明确告知且允许取消。
        Modal.confirm({
          title: t('core.plugins.disableConfirmTitle'),
          content: t('core.plugins.disableConfirmContent', {
            name: pluginName(row),
            scopes: row
              .disableImpact!.map(scope => t(`core.plugins.disableScope.${scope}`))
              .join(' / '),
          }),
          okText: t('core.plugins.disable'),
          okType: 'danger',
          cancelText: t('core.common.cancel'),
          onOk: () => {
            resolve(true)
          },
          onCancel: () => {
            resolve(false)
          },
        })
      })
      if (!confirmed) return
    }
    const result = await api.runCommand(action, {
      configUid: row.uid,
      group: 'info',
      field: action,
      value: true,
    })
    message.success(result.message || t('core.plugins.actionComplete'))
    await load()
  } catch (error) {
    message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
  } finally {
    running.value = false
  }
}
const toggleExpanded = (uid: string) => {
  // 按用户点击切换指定插件详情的展开状态。
  expandedRowKeys.value = expandedRowKeys.value.includes(uid)
    ? expandedRowKeys.value.filter(key => /* 从展开键中移除当前插件，收起对应详情。 */ key !== uid)
    : [...expandedRowKeys.value, uid]
}
const handleExpand = (expanded: boolean, row: PluginRow) => {
  // 根据表格展开事件更新展开键，避免重复添加同一插件。
  expandedRowKeys.value = expanded
    ? expandedRowKeys.value.includes(row.uid)
      ? expandedRowKeys.value
      : [...expandedRowKeys.value, row.uid]
    : expandedRowKeys.value.filter(
        key => /* 收起表格指定行时移除该插件的展开键。 */ key !== row.uid
      )
}
watch(locale, load, { immediate: true })
</script>

<template>
  <main class="plugins-page">
    <PageHeader :title="t('core.plugins.title')">
      <template #actions>
        <a-button :loading="loading" @click="load"
          ><template #icon><ReloadOutlined /></template>{{ t('core.plugins.refresh') }}</a-button
        >
        <a-button type="primary" @click="$router.push({ name: 'PluginMarket' })"
          ><template #icon><ShopOutlined /></template>{{ t('core.plugins.marketButton') }}</a-button
        >
      </template>
    </PageHeader>
    <PageSurface>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="load" />
      <a-table
        v-if="rows.length || loading"
        :data-source="rows"
        :loading="loading"
        row-key="uid"
        :pagination="false"
        :expanded-row-keys="expandedRowKeys"
        @expand="handleExpand"
      >
        <template #emptyText><span /></template>
        <a-table-column key="name" :title="t('core.plugins.attribute.name')" :width="240">
          <template #default="{ record }"
            ><div class="plugin-name-cell">
              <a class="plugin-name" @click="toggleExpanded(record.uid)">{{ pluginName(record) }}</a
              ><span class="plugin-id">{{ record.info.package_name || record.uid }}</span
              ><span class="plugin-description">{{
                pluginText(
                  record,
                  'description',
                  String(record.info.description || t('core.plugins.noDescription'))
                )
              }}</span>
            </div></template
          >
        </a-table-column>
        <a-table-column key="tags" :title="t('core.plugins.tags')" :width="180"
          ><template #default="{ record }"
            ><a-space wrap size="small"
              ><a-tag v-for="tag in tags(record)" :key="String(tag)">{{ tag }}</a-tag
              ><span v-if="!tags(record).length" class="muted">-</span></a-space
            ></template
          ></a-table-column
        >
        <a-table-column key="state" :title="t('core.plugins.attribute.status')" :width="120"
          ><template #default="{ record }"
            ><a-tag :color="statusColor(status(record))">{{
              enumText('state', status(record))
            }}</a-tag></template
          ></a-table-column
        >
        <a-table-column key="version" :title="t('core.plugins.attribute.version')" :width="120"
          ><template #default="{ record }">{{
            record.info.version || '-'
          }}</template></a-table-column
        >
        <a-table-column key="source" :title="t('core.plugins.attribute.source')" :width="120"
          ><template #default="{ record }">{{
            enumText('source', record.info.source)
          }}</template></a-table-column
        >
        <a-table-column key="error" :title="t('core.plugins.attribute.error')"
          ><template #default="{ record }"
            ><span v-if="record.info.last_error" class="error-text">{{
              record.info.last_error
            }}</span
            ><span v-else class="muted">-</span></template
          ></a-table-column
        >
        <a-table-column key="enabled" :title="t('core.plugins.attribute.enabled')" :width="90">
          <template #default="{ record }">
            <a-switch
              v-if="
                pluginActionHint(record.ui, 'info', 'enable') ||
                pluginActionHint(record.ui, 'info', 'disable')
              "
              :aria-label="`${pluginName(record)} ${t('core.plugins.attribute.enabled')}`"
              :checked="pluginToggleChecked(record.ui, record.info.enabled)"
              :disabled="
                running ||
                pluginActionHint(
                  record.ui,
                  'info',
                  pluginToggleChecked(record.ui, record.info.enabled) ? 'disable' : 'enable'
                )?.editable !== true
              "
              @change="
                trigger(
                  record,
                  pluginToggleChecked(record.ui, record.info.enabled) ? 'disable' : 'enable'
                )
              "
            />
          </template>
        </a-table-column>
        <a-table-column
          key="actions"
          :title="t('core.plugins.action')"
          :width="116"
          align="right"
          fixed="right"
        >
          <template #default="{ record }"
            ><a-space size="small"
              ><a-button
                type="text"
                :aria-label="t('core.plugins.settings')"
                @click="$router.push({ name: 'PluginSettings', params: { pluginId: record.uid } })"
                ><SettingOutlined /></a-button
              ><a-dropdown placement="bottomRight"
                ><a-button
                  type="text"
                  :disabled="running"
                  :aria-label="t('core.plugins.moreActions')"
                  ><MoreOutlined /></a-button
                ><template #overlay
                  ><a-menu
                    ><a-menu-item
                      key="reload"
                      v-if="pluginActionHint(record.ui, 'info', 'reload')"
                      :disabled="pluginActionHint(record.ui, 'info', 'reload')?.editable !== true"
                      @click="trigger(record, 'reload')"
                      >{{ t('core.plugins.reload') }}</a-menu-item
                    ><a-menu-divider /><a-menu-item
                      key="uninstall"
                      v-if="pluginActionHint(record.ui, 'info', 'uninstall')"
                      :disabled="
                        pluginActionHint(record.ui, 'info', 'uninstall')?.editable !== true
                      "
                      danger
                      @click="trigger(record, 'uninstall')"
                      >{{ t('core.plugins.uninstall') }}</a-menu-item
                    ></a-menu
                  ></template
                ></a-dropdown
              ></a-space
            ></template
          >
        </a-table-column>
        <template #expandedRowRender="{ record }"
          ><a-descriptions class="plugin-details" size="small" :column="3" bordered
            ><a-descriptions-item :label="t('core.plugins.attribute.author')">{{
              textValue(record.info.author)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.license')">{{
              textValue(record.info.license)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.requiresDist')">{{
              listValue(record.info.requires_dist)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.importName')">{{
              textValue(record.info.import_name)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.repository')">{{
              textValue(record.info.repository)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.homepage')">{{
              textValue(record.info.homepage)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.docs')">{{
              textValue(record.info.docs_url)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.requires')">{{
              listValue(record.info.requires)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.wants')">{{
              listValue(record.info.wants)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.lifecycle')">{{
              textValue(record.info.lifecycle_context)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.enabled')">{{
              flagValue(record.info.enabled)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.core')">{{
              flagValue(record.info.is_core)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.local')">{{
              flagValue(record.info.is_local)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.codeDrift')">{{
              textValue(record.info.code_drift)
            }}</a-descriptions-item
            ><a-descriptions-item :label="t('core.plugins.attribute.error')">{{
              textValue(record.info.last_error)
            }}</a-descriptions-item></a-descriptions
          ></template
        >
      </a-table>
      <NoData
        v-if="!loading && !loadError && !rows.length"
        :description="t('core.plugins.empty')"
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
.plugin-name-cell {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}
.plugin-name {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plugin-id,
.plugin-description,
.muted {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}
.plugin-description {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.error-text {
  color: var(--ant-color-error);
}
.plugin-details {
  margin: 0 8px;
}
</style>
