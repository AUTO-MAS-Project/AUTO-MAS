<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  FolderOutlined,
  FileTextOutlined,
  CloudDownloadOutlined,
  DownloadOutlined,
  CheckOutlined,
} from '@ant-design/icons-vue'
import { BetterGiService } from '@/api'
import type {
  BetterGIScriptRepoCatalogOut,
  BetterGIScriptRepoNode,
} from '@/api'

interface TreeNode {
  key: string
  title: string
  isLeaf: boolean
  node: BetterGIScriptRepoNode
  children: TreeNode[]
}

const route = useRoute()
const { t } = useI18n()
const logger = window.electronAPI.getLogger('BetterGI脚本仓库')

const scriptId = computed(() => String(route.query.scriptId || ''))

const loading = ref(false)
const catalog = ref<BetterGIScriptRepoCatalogOut | null>(null)
const activeCategory = ref<string>('')
const keyword = ref('')
const selectedNode = ref<BetterGIScriptRepoNode | null>(null)
const subscribingPath = ref<string | null>(null)
const subscribedPaths = ref<string[]>([])
const expandedKeys = ref<string[]>([])

const categoryList = computed<
  Array<{ key: string; label: string; count: number; tree: BetterGIScriptRepoNode[] }>
>(() => {
  const cats = catalog.value?.categories || {}
  const count = (nodes: BetterGIScriptRepoNode[]): number =>
    nodes.reduce((acc, n) => acc + 1 + count(n.children || []), 0)
  return Object.entries(cats).map(([key, c]) => ({
    key,
    label: c.label || key,
    count: count(c.tree || []),
    tree: c.tree || [],
  }))
})

const filterTree = (nodes: BetterGIScriptRepoNode[], kw: string): BetterGIScriptRepoNode[] => {
  const out: BetterGIScriptRepoNode[] = []
  for (const n of nodes) {
    const children = filterTree(n.children || [], kw)
    const self =
      n.name.toLowerCase().includes(kw) || (n.description || '').toLowerCase().includes(kw)
    if (self || children.length) out.push({ ...n, children })
  }
  return out
}

const collectKeys = (nodes: BetterGIScriptRepoNode[]): string[] =>
  nodes.flatMap((n) => [n.path, ...collectKeys(n.children || [])])

const toTreeData = (nodes: BetterGIScriptRepoNode[]): TreeNode[] =>
  nodes.map((n) => ({
    key: n.path,
    title: n.name,
    isLeaf: n.type !== 'directory' || !(n.children && n.children.length),
    node: n,
    children: toTreeData(n.children || []),
  }))

const displayedTree = computed<TreeNode[]>(() => {
  const cat = categoryList.value.find((c) => c.key === activeCategory.value)
  const tree = cat ? cat.tree : []
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return toTreeData(tree)
  const filtered = filterTree(tree, kw)
  expandedKeys.value = collectKeys(filtered)
  return toTreeData(filtered)
})

const fetchCatalog = async () => {
  if (!scriptId.value) {
    message.error(t('edit.bettergiScriptRepoInvalidId'))
    return
  }
  loading.value = true
  try {
    const resp =
      await BetterGiService.getBettergiScriptRepoCatalogApiApiScriptsBettergiScriptRepoCatalogGet(
        scriptId.value,
      )
    if (resp.status !== 'success') {
      message.error(resp.message || t('edit.bettergiScriptRepoLoadFailed'))
      catalog.value = { repoExists: false }
      return
    }
    catalog.value = resp
    const keys = Object.keys(resp.categories || {})
    if (!activeCategory.value || !keys.includes(activeCategory.value)) {
      activeCategory.value = keys.includes('js') ? 'js' : (keys[0] || '')
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(t('edit.bettergiScriptRepoLoadFailed'))
  } finally {
    loading.value = false
  }
}

watch(activeCategory, () => {
  selectedNode.value = null
  expandedKeys.value = []
  keyword.value = ''
})

onMounted(() => void fetchCatalog())
watch(
  () => route.query.scriptId,
  (v) => {
    if (v) void fetchCatalog()
  },
)

const onSelect = (keys: Array<string | number>) => {
  if (!keys.length) return
  const find = (nodes: BetterGIScriptRepoNode[]): BetterGIScriptRepoNode | null => {
    for (const n of nodes) {
      if (n.path === keys[0]) return n
      const hit = find(n.children || [])
      if (hit) return hit
    }
    return null
  }
  const cat = categoryList.value.find((c) => c.key === activeCategory.value)
  selectedNode.value = cat ? find(cat.tree) : null
}

const doSubscribe = async (node: BetterGIScriptRepoNode, immediate: boolean) => {
  if (subscribingPath.value) return
  subscribingPath.value = node.path
  try {
    const resp =
      await BetterGiService.subscribeBettergiScriptRepoApiApiScriptsBettergiScriptRepoSubscribePost(
        { scriptId: scriptId.value, path: node.path, immediate },
      )
    if (resp.status === 'success') {
      if (!subscribedPaths.value.includes(node.path)) subscribedPaths.value.push(node.path)
      message.success(
        resp.message ||
          (immediate ? t('edit.bettergiScriptRepoDeployed') : t('edit.bettergiScriptRepoSubscribed')),
      )
    } else {
      message.error(resp.message || t('edit.bettergiScriptRepoSubscribeFailed'))
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(t('edit.bettergiScriptRepoSubscribeFailed'))
  } finally {
    subscribingPath.value = null
  }
}
</script>

<template>
  <div class="repo-page">
    <div v-if="loading" class="repo-loading">
      <a-spin />
      <span>{{ t('edit.bettergiScriptRepoLoading') }}</span>
    </div>
    <a-empty
      v-else-if="!catalog || !catalog.repoExists"
      :description="t('edit.bettergiScriptRepoEmpty')"
    />
    <div v-else class="repo-body">
      <div class="repo-toolbar">
        <a-tabs v-model:activeKey="activeCategory" class="repo-tabs">
          <a-tab-pane
            v-for="c in categoryList"
            :key="c.key"
            :tab="`${c.label} (${c.count})`"
          />
        </a-tabs>
        <a-input-search
          v-model:value="keyword"
          :placeholder="t('edit.bettergiScriptRepoSearchPlaceholder')"
          allow-clear
          class="repo-search"
        />
      </div>
      <div class="repo-tree-wrap">
        <a-tree
          v-if="displayedTree.length"
          :tree-data="displayedTree"
          :expanded-keys="expandedKeys"
          block-node
          :selectable="true"
          @expand="(keys: any) => (expandedKeys = keys as string[])"
          @select="onSelect"
        >
          <template #title="data">
            <span class="repo-node">
              <FolderOutlined v-if="!data.isLeaf" class="repo-node-icon" />
              <FileTextOutlined v-else class="repo-node-icon" />
              <span class="repo-node-name">{{ data.title }}</span>
              <a-tag
                v-if="data.node?.version"
                class="repo-node-version"
                color="blue"
              >v{{ data.node?.version }}</a-tag>
            </span>
          </template>
        </a-tree>
        <a-empty v-else :description="t('edit.bettergiScriptRepoNoMatch')" />
      </div>
      <div v-if="selectedNode" class="repo-detail">
        <div class="repo-detail-head">
          <span class="repo-detail-name">{{ selectedNode.name }}</span>
          <span v-if="selectedNode.author" class="repo-detail-meta">
            {{ selectedNode.author }}
          </span>
          <span v-if="selectedNode.lastUpdated" class="repo-detail-meta">
            {{ selectedNode.lastUpdated }}
          </span>
        </div>
        <div v-if="selectedNode.description" class="repo-detail-desc">
          {{ selectedNode.description }}
        </div>
        <div v-if="selectedNode.tags && selectedNode.tags.length" class="repo-detail-tags">
          <a-tag v-for="tag in selectedNode.tags" :key="tag">{{ tag }}</a-tag>
        </div>
        <div class="repo-detail-actions">
          <a-button
            type="primary"
            size="small"
            :loading="subscribingPath === selectedNode.path"
            :disabled="subscribedPaths.includes(selectedNode.path)"
            @click="doSubscribe(selectedNode, false)"
          >
            <template #icon>
              <CheckOutlined v-if="subscribedPaths.includes(selectedNode.path)" />
              <CloudDownloadOutlined v-else />
            </template>
            {{
              subscribedPaths.includes(selectedNode.path)
                ? t('edit.bettergiScriptRepoAlreadySubscribed')
                : t('edit.bettergiScriptRepoSubscribe')
            }}
          </a-button>
          <a-button
            size="small"
            :loading="subscribingPath === selectedNode.path"
            :disabled="subscribingPath === selectedNode.path"
            @click="doSubscribe(selectedNode, true)"
          >
            <template #icon><DownloadOutlined /></template>
            {{ t('edit.bettergiScriptRepoSubscribeNow') }}
          </a-button>
          <span class="repo-detail-hint">{{ t('edit.bettergiScriptRepoSubscribeHint') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.repo-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 16px;
  box-sizing: border-box;
  gap: 8px;
}
.repo-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 0;
  color: var(--text-color-secondary, #888);
}
.repo-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 0;
}
.repo-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.repo-tabs {
  flex: 1;
}
.repo-search {
  width: 220px;
  margin-top: 4px;
}
.repo-tree-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  border: 1px solid var(--border-color-split, #f0f0f0);
  border-radius: 6px;
  padding: 4px;
}
.repo-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.repo-node-icon {
  color: var(--primary-color, #1677ff);
  flex-shrink: 0;
}
.repo-node-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.repo-node-version {
  margin-inline-start: 4px;
  font-size: 11px;
  line-height: 16px;
  padding: 0 4px;
}
.repo-detail {
  border-top: 1px solid var(--border-color-split, #f0f0f0);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.repo-detail-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.repo-detail-name {
  font-weight: 600;
  word-break: break-all;
}
.repo-detail-meta {
  font-size: 12px;
  color: var(--text-color-secondary, #888);
}
.repo-detail-desc {
  font-size: 12px;
  color: var(--text-color-secondary, #888);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.repo-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.repo-detail-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.repo-detail-hint {
  font-size: 12px;
  color: var(--text-color-secondary, #888);
}
</style>
