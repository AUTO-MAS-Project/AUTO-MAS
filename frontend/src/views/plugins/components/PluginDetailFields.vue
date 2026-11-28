<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { handleExternalLink } from '@/utils/openExternal'
import {
  detailFieldKeys,
  joinSegments,
  sourceLabelKey,
  type DetailFieldKey,
  type PluginView,
} from '../pluginCenterModel'

/**
 * 已安装展开区与市场详情共用的信息块：描述、字段网格、三类链接。
 * 缺哪项不显示哪项；三类链接都没有时整行不出现。诊断信息只属于已安装，由调用方放在默认插槽。
 */
const props = withDefaults(defineProps<{ view: PluginView; minColumnWidth?: number }>(), {
  minColumnWidth: 180,
})
const { t } = useI18n()

const LABELS: Record<DetailFieldKey, string> = {
  author: 'core.plugins.attribute.author',
  license: 'core.plugins.attribute.license',
  publisher: 'core.plugins.attribute.publisher',
  source: 'core.plugins.attribute.source',
  packageName: 'core.plugins.attribute.packageName',
  tags: 'core.plugins.tags',
  dependencies: 'core.plugins.attribute.dependencies',
}

const fields = computed(() => detailFieldKeys(props.view))
const textOf = (key: DetailFieldKey): string => {
  const view = props.view
  if (key === 'author') return view.author ?? ''
  if (key === 'license') return view.license ?? ''
  if (key === 'packageName') return view.packageName ?? ''
  if (key === 'publisher')
    return view.publisher ? t(`core.plugins.publisher.${view.publisher}`) : ''
  if (key === 'source' && view.kind === 'installed') {
    const labelKey = sourceLabelKey(view.source)
    return joinSegments([labelKey ? t(labelKey) : view.source, view.packageName])
  }
  return ''
}
</script>

<template>
  <div class="plugin-metadata">
    <p v-if="view.description" class="plugin-metadata-description">{{ view.description }}</p>
    <dl
      v-if="fields.length"
      class="plugin-metadata-fields"
      :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${minColumnWidth}px, 1fr))` }"
    >
      <div v-for="key in fields" :key="key" class="plugin-metadata-field">
        <dt>{{ t(LABELS[key]) }}</dt>
        <dd v-if="key === 'tags'">
          <a-space wrap :size="4">
            <a-tag v-for="tag in view.tags" :key="tag" :bordered="false">{{ tag }}</a-tag>
          </a-space>
        </dd>
        <dd v-else-if="key === 'dependencies'">
          <div v-for="line in view.dependencies" :key="line" class="plugin-metadata-dependency">
            {{ line }}
          </div>
        </dd>
        <dd v-else>{{ textOf(key) }}</dd>
      </div>
    </dl>
    <div v-if="view.links.length" class="plugin-metadata-links">
      <a
        v-for="link in view.links"
        :key="link.kind"
        :href="link.href"
        target="_blank"
        rel="noopener noreferrer"
        @click="handleExternalLink"
        >{{ t(`core.plugins.link.${link.kind}`) }}</a
      >
    </div>
    <slot />
  </div>
</template>

<style scoped>
.plugin-metadata {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
  overflow-wrap: anywhere;
}

.plugin-metadata-description {
  margin: 0;
}

.plugin-metadata-fields {
  display: grid;
  margin: 0;
  gap: 12px 24px;
}

.plugin-metadata-field {
  min-width: 0;
}

.plugin-metadata-field dt {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
}

.plugin-metadata-field dd {
  margin: 0;
}

.plugin-metadata-dependency {
  font-family: var(--font-monospace);
  font-size: 12px;
}

.plugin-metadata-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}
</style>
