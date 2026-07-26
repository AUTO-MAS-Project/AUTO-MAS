<template>
  <section class="detail-card" aria-label="插件实例配置">
    <header class="detail-header">
      <div class="detail-title">
        <span>{{ selectedInstance ? selectedInstance.plugin : '实例配置' }}</span>
        <span v-if="selectedInstance" class="detail-instance-id">{{ editForm.instanceId }}</span>
      </div>
      <div v-if="selectedInstance" class="detail-actions">
        <a-button type="primary" :loading="submitting" @click="submitEdit"> 保存配置 </a-button>
        <a-button :disabled="!isDirty" @click="resetEdit">重置改动</a-button>
        <a-button @click="$emit('openJsonPreview')">查看当前 JSON</a-button>
        <a-button @click="$emit('reloadInstance', editForm.instanceId)">重载实例</a-button>
        <a-button @click="$emit('reloadPlugin', editForm.plugin)">重载同插件</a-button>
        <a-popconfirm
          :disabled="!canUninstall || uninstallingPlugin === editForm.plugin"
          :title="`确认卸载插件包 ${selectedPluginPackageName || editForm.plugin}？相关实例配置不会自动删除。`"
          ok-text="卸载"
          cancel-text="取消"
          @confirm="$emit('uninstallPlugin', editForm.plugin)"
        >
          <a-button
            danger
            :disabled="!canUninstall"
            :loading="uninstallingPlugin === editForm.plugin"
          >
            卸载插件
          </a-button>
        </a-popconfirm>
        <a-popconfirm
          title="确认删除该实例？"
          :disabled="Boolean(selectedInstance?.locked)"
          @confirm="$emit('deleteInstance', editForm.instanceId)"
        >
          <a-button danger :disabled="Boolean(selectedInstance?.locked)">删除实例</a-button>
        </a-popconfirm>
      </div>
    </header>

    <div class="detail-scroll" @wheel.stop>
      <template v-if="selectedInstance">
        <a-alert
          v-if="isDirty"
          type="warning"
          show-icon
          message="当前有未保存改动"
          style="margin-bottom: 12px"
        />

        <a-alert
          v-if="currentSchemaError"
          type="error"
          show-icon
          :message="`Schema 加载失败：${currentSchemaError}`"
          style="margin-bottom: 12px"
        />

        <a-alert
          v-if="!currentSchemaError && activeSchemaEntries.length === 0"
          type="warning"
          show-icon
          message="该插件未声明 schema，可能非预期行为或插件本身无需配置"
          style="margin-bottom: 12px"
        />

        <a-alert
          v-if="hasServiceDeclarations"
          class="service-alert"
          type="info"
          show-icon
          message="服务声明"
        >
          <template #description>
            <div class="service-declaration-list">
              <div
                v-for="row in serviceDeclarationRows"
                :key="row.key"
                class="service-declaration-row"
              >
                <a-tag :color="row.color" class="service-declaration-label">
                  {{ row.label }}
                </a-tag>
                <span class="service-declaration-value">{{ row.value }}</span>
              </div>
            </div>
          </template>
        </a-alert>

        <section v-if="pluginActions.length > 0" class="surface-group plugin-action-card">
          <h3 class="surface-group-title">插件动作</h3>
          <a-space wrap>
            <a-button
              v-for="item in pluginActions"
              :key="item.id"
              type="primary"
              :loading="actionLoadingId === item.id"
              :disabled="Boolean(actionLoadingId)"
              @click="$emit('triggerAction', item)"
            >
              {{ item.label }}
            </a-button>
          </a-space>
        </section>

        <PluginLifecycleState
          v-if="runtimeState"
          :runtime-state="runtimeState"
          :show-details="true"
          @reload="$emit('reloadInstance', editForm.instanceId)"
          @copy-diagnostics="$emit('copyDiagnostics')"
        />

        <a-form layout="vertical">
          <a-form-item label="实例名称">
            <a-input
              :value="editForm.name"
              placeholder="输入实例名称"
              @update:value="(val: string) => $emit('update:editForm', { ...editForm, name: val })"
            />
          </a-form-item>

          <section class="surface-group editor-card">
            <h3 class="surface-group-title">插件配置</h3>
            <template v-if="activeSchemaEntries.length > 0">
              <SchemaForm
                ref="schemaFormRef"
                v-model="schemaFormModel"
                :schema="activeSchema"
                layout="plugin-grid"
                :hide-fields="hiddenSchemaFields"
                :action-loading-id="actionLoadingId"
                @trigger-action="
                  ({ field, fieldSchema }: any) =>
                    $emit('triggerSchemaAction', field, fieldSchema as any)
                "
                @validation-change="
                  (errors: Record<string, string>) => $emit('validationChange', errors)
                "
                @sensitive-dirty-change="$emit('sensitiveDirtyChange', $event)"
              />
            </template>
            <template v-else>
              <a-form-item label="配置 JSON（Schema 不可用时可直接编辑）" style="margin-bottom: 0">
                <a-textarea
                  :value="editForm.configText"
                  :rows="12"
                  placeholder="请输入 JSON 对象配置"
                  @update:value="
                    (val: string) => $emit('update:editForm', { ...editForm, configText: val })
                  "
                />
              </a-form-item>
            </template>
          </section>
        </a-form>
      </template>

      <div v-else class="detail-empty">
        <span class="detail-empty-title">尚未选择实例</span>
        <span class="detail-empty-hint">从左侧列表选择一个实例，即可查看运行状态并编辑配置。</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import SchemaForm from '@/components/SchemaForm.vue'
import PluginLifecycleState from './PluginLifecycleState.vue'
import type {
  PluginInstance,
  PluginSchemaField,
  PluginRuntimeState,
  PluginActionInfo,
  PluginServiceInfo,
  ServiceDeclarationRow,
} from '../types'
import { SERVICE_DECLARATION_DEFS } from '../types'
import { parseConfigText } from '../composables/usePluginSchema'

defineOptions({ name: 'PluginInstanceDetail' })

interface EditForm {
  instanceId: string
  plugin: string
  name: string
  enabled: boolean
  configText: string
}

const props = defineProps<{
  selectedInstance: PluginInstance | null
  editForm: EditForm
  isDirty: boolean
  editSnapshot: string
  submitting: boolean
  actionLoadingId: string
  uninstallingPlugin: string
  // Schema
  activeSchema: Record<string, PluginSchemaField>
  activeSchemaEntries: [string, PluginSchemaField][]
  currentSchemaError: string
  hiddenSchemaFields: string[]
  // Runtime
  runtimeState: PluginRuntimeState | null
  // Services
  selectedPluginService: PluginServiceInfo | null
  // Actions
  pluginActions: PluginActionInfo[]
  // Package
  selectedPluginPackageName: string
  canUninstall: boolean
}>()

const emit = defineEmits<{
  (e: 'submitEdit', configPatch?: Record<string, unknown>): void
  (e: 'resetEdit'): void
  (e: 'openJsonPreview'): void
  (e: 'reloadInstance', instanceId: string): void
  (e: 'reloadPlugin', plugin: string): void
  (e: 'uninstallPlugin', plugin: string): void
  (e: 'deleteInstance', instanceId: string): void
  (e: 'triggerAction', action: PluginActionInfo): void
  (e: 'triggerSchemaAction', field: string, fieldSchema: PluginSchemaField): void
  (e: 'validationChange', errors: Record<string, string>): void
  (e: 'sensitiveDirtyChange', dirty: boolean): void
  (e: 'update:editForm', form: EditForm): void
  (e: 'copyDiagnostics'): void
}>()

const schemaFormRef = ref<InstanceType<typeof SchemaForm> | null>(null)

const schemaFormModel = computed<Record<string, unknown>>({
  get: () => {
    try {
      return parseConfigText(props.editForm.configText)
    } catch {
      return {}
    }
  },
  set: value => {
    emit('update:editForm', {
      ...props.editForm,
      configText: JSON.stringify(value, null, 2),
    })
  },
})

const submitEdit = () => {
  const configPatch =
    props.activeSchemaEntries.length > 0
      ? schemaFormRef.value?.buildSavePayload()
      : schemaFormModel.value
  emit('submitEdit', configPatch)
}

const resetSensitiveDrafts = () => {
  schemaFormRef.value?.resetSensitiveDrafts()
  emit('sensitiveDirtyChange', false)
}

const validateSchema = (): Record<string, string> => {
  return schemaFormRef.value?.validate()?.errors || {}
}

const resetEdit = () => {
  resetSensitiveDrafts()
  emit('resetEdit')
}

defineExpose({
  resetSensitiveDrafts,
  validateSchema,
})

const hasServiceListItems = (items?: string[]) => Array.isArray(items) && items.length > 0

const serviceDeclarationRows = computed<ServiceDeclarationRow[]>(() => {
  const service = props.selectedPluginService
  if (!service) return []
  return SERVICE_DECLARATION_DEFS.map((item): ServiceDeclarationRow | null => {
    const values = service[item.key]
    if (!hasServiceListItems(values)) return null
    return { key: item.key, label: item.label, color: item.color, value: values.join('、') }
  }).filter((item): item is ServiceDeclarationRow => item !== null)
})

const hasServiceDeclarations = computed(() => serviceDeclarationRows.value.length > 0)
</script>

<style scoped>
.detail-card {
  height: 100%;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
  min-height: 52px;
  padding: var(--v6-space-2) var(--v6-space-4);
  border-bottom: 0.5px solid var(--v6-color-border-subtle);
}

.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--v6-space-4) var(--v6-space-4) calc(var(--v6-space-6) + var(--v6-space-2));
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.detail-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.detail-title {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  min-width: 0;
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
}

.detail-instance-id {
  max-width: 320px;
  overflow: hidden;
  color: var(--v6-color-text-tertiary);
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-normal);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--v6-space-2);
  min-width: 0;
  flex-wrap: wrap;
}

.editor-card {
  margin-bottom: 10px;
}

.plugin-action-card {
  margin-bottom: 10px;
}

/* 分隔线分组：避免大框内再嵌套细边小卡 */
.surface-group {
  padding: var(--v6-space-3) 0 0;
  border-top: 0.5px solid var(--v6-color-border-subtle);
}

.surface-group-title {
  margin: 0 0 var(--v6-space-3);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-semibold);
}

.service-alert {
  margin-bottom: 10px;
}

.service-declaration-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.service-declaration-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.service-declaration-label {
  flex: 0 0 auto;
  margin-inline-end: 0;
}

.service-declaration-value {
  min-width: 0;
  word-break: break-word;
}

.detail-empty {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-1);
  max-width: 420px;
  margin: var(--v6-space-6) auto 0;
  padding: var(--v6-space-4);
  border: 1.5px dashed var(--v6-color-border);
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-content);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  text-align: center;
}

.detail-empty-title {
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
}

.detail-empty-hint {
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  line-height: var(--v6-line-height-normal);
}

@container plugin-page (max-width: 1180px) {
  .detail-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .detail-actions {
    justify-content: flex-start;
  }
}
</style>
