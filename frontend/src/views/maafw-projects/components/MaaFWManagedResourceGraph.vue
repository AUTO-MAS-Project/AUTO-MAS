<template>
  <section class="resource-graph" aria-labelledby="maafw-resource-graph-title">
    <div class="graph-heading">
      <div>
        <h3 id="maafw-resource-graph-title">资源关系图</h3>
        <p>按脚本、项目版本、运行依赖和实际目录查看当前只读盘点结果。</p>
      </div>
      <a-space>
        <a-tag color="blue">只读</a-tag>
        <a-button
          v-if="hasGarbageCandidates"
          type="link"
          size="small"
          @click="goToGarbageCollection"
        >
          查看孤儿回收预览
        </a-button>
      </a-space>
    </div>

    <a-empty v-if="!graphNodes.length" description="暂无可绘制的资源关系" />

    <template v-else>
      <div class="graph-flow" aria-hidden="true">
        <span>脚本</span>
        <ArrowRightOutlined />
        <span>项目版本</span>
        <ArrowRightOutlined />
        <span>MaaFW 版本 / 依赖</span>
        <ArrowRightOutlined />
        <span>资源目录</span>
      </div>

      <div class="graph-board">
        <div class="graph-columns">
          <section v-for="column in graphColumns" :key="column.key" class="graph-column">
            <div class="column-heading">
              <strong>{{ column.label }}</strong>
              <a-typography-text type="secondary">{{ column.nodes.length }}</a-typography-text>
            </div>
            <div class="graph-node-list">
              <button
                v-for="node in column.nodes"
                :key="node.id"
                type="button"
                class="graph-node"
                :class="{ 'graph-node-selected': selectedNodeId === node.id }"
                :aria-pressed="selectedNodeId === node.id"
                @click="selectNode(node.id)"
              >
                <span class="node-heading">
                  <a-tag :color="nodeColor(node.kind)">{{ nodeKindLabel(node.kind) }}</a-tag>
                  <strong>{{ node.title }}</strong>
                </span>
                <span v-if="node.subtitle" class="node-subtitle">{{ node.subtitle }}</span>
                <span v-if="node.badges.length" class="node-badges">
                  <span v-for="badge in node.badges" :key="badge" class="node-badge">
                    {{ badge }}
                  </span>
                </span>
              </button>
            </div>
          </section>
        </div>
      </div>

      <div v-if="selectedNode" class="graph-details">
        <div class="details-heading">
          <div>
            <h4>{{ selectedNode.title }}</h4>
            <p>{{ selectedNode.subtitle || nodeKindLabel(selectedNode.kind) }}</p>
          </div>
          <a-tag :color="nodeColor(selectedNode.kind)">
            {{ nodeKindLabel(selectedNode.kind) }}
          </a-tag>
        </div>
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item
            v-for="item in selectedNode.details"
            :key="item.label"
            :label="item.label"
          >
            <a-typography-text
              v-if="item.copyable"
              :copyable="{ text: item.value }"
              class="detail-value"
            >
              {{ item.value || '—' }}
            </a-typography-text>
            <span v-else>{{ item.value || '—' }}</span>
          </a-descriptions-item>
        </a-descriptions>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRightOutlined } from '@ant-design/icons-vue'
import {
  buildResourceGraphColumns,
  type GraphNode,
  type GraphNodeKind,
} from './MaaFWManagedResourceGraphModel'
import type { MaaFWManagedGlobalInventory } from '@/composables/useMaaFWManagedApi'

defineOptions({ name: 'MaaFWManagedResourceGraph' })

const props = defineProps<{
  inventory: MaaFWManagedGlobalInventory
}>()

const selectedNodeId = ref('')
const graphColumns = computed(() => buildResourceGraphColumns(props.inventory))
const graphNodes = computed(() => graphColumns.value.flatMap(column => column.nodes))
const selectedNode = computed<GraphNode | null>(
  () => graphNodes.value.find(node => node.id === selectedNodeId.value) || null
)
const hasGarbageCandidates = computed(() =>
  graphNodes.value.some(node => node.badges.includes('无引用'))
)

watch(
  graphNodes,
  nodes => {
    if (!nodes.some(node => node.id === selectedNodeId.value))
      selectedNodeId.value = nodes[0]?.id || ''
  },
  { immediate: true }
)

const selectNode = (nodeId: string) => {
  selectedNodeId.value = nodeId
}

const goToGarbageCollection = () => {
  document.getElementById('maafw-global-gc')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const nodeKindLabel = (kind: GraphNodeKind) => {
  const labels: Record<GraphNodeKind, string> = {
    script: '脚本',
    version: '版本',
    dependency: '依赖',
    runtime: '运行时',
    directory: '目录',
  }
  return labels[kind]
}

const nodeColor = (kind: GraphNodeKind) => {
  const colors: Record<GraphNodeKind, string> = {
    script: 'blue',
    version: 'green',
    dependency: 'gold',
    runtime: 'purple',
    directory: 'cyan',
  }
  return colors[kind]
}
</script>

<style scoped>
.resource-graph {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 24px;
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.graph-heading,
.details-heading,
.column-heading,
.node-heading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.graph-heading,
.details-heading {
  justify-content: space-between;
  align-items: flex-start;
}

.graph-heading h3,
.details-heading h4 {
  margin: 0 0 4px;
  color: var(--ant-color-text);
}

.graph-heading p,
.details-heading p {
  margin: 0;
  color: var(--ant-color-text-secondary);
}

.graph-flow {
  display: grid;
  grid-template-columns: 1fr 28px 1fr 28px 1fr 28px 1fr;
  align-items: center;
  min-width: 900px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  text-align: center;
}

.graph-flow svg {
  color: var(--ant-color-primary);
  font-size: 16px;
}

.graph-board {
  overflow-x: auto;
  padding-bottom: 4px;
}

.graph-columns {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 12px;
  min-width: 900px;
}

.graph-column {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.column-heading {
  justify-content: space-between;
  min-height: 24px;
  margin-bottom: 10px;
  color: var(--ant-color-text);
}

.graph-node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.graph-node {
  display: flex;
  width: 100%;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease,
    box-shadow 0.15s ease;
}

.graph-node:hover,
.graph-node:focus-visible {
  border-color: var(--ant-color-primary);
  outline: none;
}

.graph-node-selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg-hover);
}

.node-heading {
  width: 100%;
  align-items: flex-start;
}

.node-heading strong {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 20px;
}

.node-subtitle {
  width: 100%;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.node-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.node-badge {
  padding: 1px 6px;
  border-radius: 10px;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-secondary);
  font-size: 11px;
  line-height: 18px;
}

.graph-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}

.detail-value {
  max-width: 100%;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .resource-graph {
    padding: 12px;
  }
}
</style>
