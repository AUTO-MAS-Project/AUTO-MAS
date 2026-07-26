<template>
  <a-modal
    :open="visible"
    title="新增插件实例"
    :confirm-loading="submitting"
    width="1040px"
    :ok-button-props="{ disabled: !addForm.plugin }"
    @ok="$emit('submitAdd')"
    @cancel="$emit('close')"
  >
    <div class="add-plugin-modal-body">
      <a-row :gutter="12" class="add-plugin-layout">
        <a-col :span="15" class="add-plugin-layout-col">
          <div class="add-plugin-picker-panel">
            <div class="add-plugin-panel-header">
              <div>
                <div class="add-plugin-panel-title">选择插件</div>
                <div class="add-plugin-panel-hint">
                  按插件名、服务声明或路由信息搜索，快速定位目标插件
                </div>
              </div>
              <a-tag color="blue">共 {{ discoveredPlugins.length }} 个</a-tag>
            </div>

            <a-input
              v-model:value="localKeyword"
              allow-clear
              placeholder="搜索插件名 / 服务 / 路由"
              class="add-plugin-search"
            />

            <div class="add-plugin-picker-summary">
              <span>筛选结果 {{ filteredOptions.length }} 个</span>
              <span v-if="localKeyword.trim()">关键词：{{ localKeyword.trim() }}</span>
            </div>

            <div class="plugin-option-grid">
              <a-empty
                v-if="filteredOptions.length === 0"
                :description="localKeyword.trim() ? '没有匹配的插件' : '当前没有可新增的插件'"
              />
              <button
                v-for="item in filteredOptions"
                :key="item.name"
                type="button"
                class="plugin-option-card"
                :class="{ active: addForm.plugin === item.name }"
                @click="$emit('update:addPlugin', item.name)"
              >
                <div class="plugin-option-card-head">
                  <span class="plugin-option-name">{{ item.name }}</span>
                  <a-tag v-if="item.instanceCount > 0" color="default">
                    {{ item.instanceCount }} 实例
                  </a-tag>
                </div>
                <div class="plugin-option-description">{{ item.description }}</div>
                <a-space class="plugin-option-tags" :size="[0, 8]" wrap>
                  <a-tag v-if="item.serviceCount > 0" color="green">
                    服务 {{ item.serviceCount }}
                  </a-tag>
                  <a-tag v-if="item.routeCount > 0" color="geekblue">
                    路由 {{ item.routeCount }}
                  </a-tag>
                  <a-tag v-if="item.schemaError" color="red">Schema 异常</a-tag>
                </a-space>
              </button>
            </div>
          </div>
        </a-col>

        <a-col :span="9" class="add-plugin-layout-col">
          <a-card size="small" title="实例信息" class="add-plugin-side-card">
            <a-form layout="vertical">
              <a-form-item label="已选插件" required>
                <a-input :value="addForm.plugin" readonly placeholder="请先选择左侧插件" />
              </a-form-item>
              <a-form-item label="实例名称">
                <a-input
                  :value="addForm.name"
                  placeholder="可选"
                  @update:value="(val: string) => $emit('update:addName', val)"
                />
              </a-form-item>
              <a-form-item label="启用">
                <a-switch
                  :checked="addForm.enabled"
                  @update:checked="(val: boolean) => $emit('update:addEnabled', val)"
                />
              </a-form-item>
            </a-form>

            <template v-if="selectedAddPluginOption">
              <a-space class="add-plugin-side-tags" :size="[0, 8]" wrap>
                <a-tag color="default">实例 {{ selectedAddPluginOption.instanceCount }}</a-tag>
                <a-tag v-if="selectedAddPluginOption.serviceCount > 0" color="green">
                  服务 {{ selectedAddPluginOption.serviceCount }}
                </a-tag>
                <a-tag v-if="selectedAddPluginOption.routeCount > 0" color="geekblue">
                  路由 {{ selectedAddPluginOption.routeCount }}
                </a-tag>
              </a-space>

              <a-alert
                v-if="selectedAddPluginOption.schemaError"
                class="add-plugin-schema-alert"
                type="warning"
                show-icon
                :message="selectedAddPluginOption.schemaError"
              />

              <div
                v-if="selectedAddPluginServiceRows.length > 0"
                class="add-plugin-service-summary"
              >
                <div
                  v-for="row in selectedAddPluginServiceRows"
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
          </a-card>
        </a-col>
      </a-row>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DiscoveredPluginOption, ServiceDeclarationRow } from '../types'

defineOptions({ name: 'PluginAddModal' })

const props = defineProps<{
  visible: boolean
  submitting: boolean
  addForm: {
    plugin: string
    name: string
    enabled: boolean
  }
  keyword: string
  discoveredPlugins: DiscoveredPluginOption[]
  filteredOptions: DiscoveredPluginOption[]
  selectedAddPluginOption: DiscoveredPluginOption | null
  selectedAddPluginServiceRows: ServiceDeclarationRow[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'submitAdd'): void
  (e: 'update:addPlugin', plugin: string): void
  (e: 'update:addName', name: string): void
  (e: 'update:addEnabled', enabled: boolean): void
  (e: 'update:keyword', keyword: string): void
}>()

const localKeyword = computed({
  get: () => props.keyword,
  set: value => emit('update:keyword', value),
})
</script>

<style scoped>
.add-plugin-modal-body {
  /* 弹窗宽度固定 1040px 且内容脱离页面 DOM(teleport),
     视口 @media 对内部网格无意义,在内容根声明容器驱动内部响应式 */
  container: plugin-add-modal / inline-size;
  min-height: 0;
}

.add-plugin-layout {
  align-items: stretch;
}

.add-plugin-layout-col {
  display: flex;
}

.add-plugin-picker-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  width: 100%;
}

.add-plugin-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.add-plugin-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.add-plugin-panel-hint {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--ant-color-text-secondary);
}

.add-plugin-search {
  margin-bottom: 6px;
}

.add-plugin-picker-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 11px;
  color: var(--ant-color-text-secondary);
}

.plugin-option-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  max-height: 468px;
  overflow: auto;
  padding-right: 2px;
}

.plugin-option-card {
  appearance: none;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--ant-color-border);
  border-radius: 10px;
  padding: 11px 12px 10px;
  text-align: left;
  background: var(
    --app-background-panel-bg,
    var(--app-background-card-bg, var(--ant-color-bg-container))
  );
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.plugin-option-card:hover {
  border-color: var(--ant-color-primary-hover);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.plugin-option-card.active {
  border-color: var(--ant-color-primary);
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--ant-color-primary-bg) 82%, transparent),
    color-mix(
      in srgb,
      var(--app-background-panel-bg, var(--app-background-card-bg, var(--ant-color-bg-container)))
        72%,
      var(--ant-color-primary-bg)
    )
  );
  box-shadow: 0 8px 22px color-mix(in srgb, var(--ant-color-primary) 14%, transparent);
}

.plugin-option-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 6px;
}

.plugin-option-name {
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.plugin-option-description {
  flex: 1;
  min-height: 32px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--ant-color-text-secondary);
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.plugin-option-tags {
  margin-top: auto;
  padding-top: 8px;
  min-height: 26px;
  align-items: flex-end;
  align-content: flex-end;
}

.plugin-option-tags:empty {
  display: none;
}

.add-plugin-side-card {
  border-color: var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--app-background-card-elevated-bg, var(--ant-color-bg-container));
  width: 100%;
}

.add-plugin-side-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
}

.add-plugin-side-tags {
  display: flex;
}

.add-plugin-schema-alert {
  margin-bottom: 0;
}

.add-plugin-service-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
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

/* 按弹窗内容实际宽度响应(窗口收窄时 antd 弹窗会随视口收缩)。
   内容根宽度≈弹窗宽度-左右 padding,阈值相应换算:
   选择面板占 15/24 列,~600px 内容宽以下先降 2 列,再降 1 列 */
@container plugin-add-modal (max-width: 900px) {
  .plugin-option-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@container plugin-add-modal (max-width: 640px) {
  .plugin-option-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
