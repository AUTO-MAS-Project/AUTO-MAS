<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CopyOutlined } from '@ant-design/icons-vue'
import { copyDevtoolsText } from './helpers'
import type { RouteVisit } from './types'

defineProps<{ history: RouteVisit[] }>()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const search = ref('')
const targetPath = ref('')
const navigating = ref(false)
const currentRoute = computed(() =>
  JSON.stringify(
    {
      name: route.name,
      params: route.params,
      query: route.query,
      matched: route.matched.map(record => record.path),
    },
    null,
    2
  )
)
const registeredRoutes = computed(() => {
  const query = search.value.toLowerCase()
  return router
    .getRoutes()
    .filter(
      record =>
        !record.redirect &&
        `${record.path} ${String(record.name)} ${String(record.meta.title ?? '')}`
          .toLowerCase()
          .includes(query)
    )
    .map(record => ({
      path: record.path,
      name: String(record.name ?? ''),
      title: record.meta.title,
    }))
    .sort((left, right) => left.path.localeCompare(right.path))
})
const columns = computed(() => [
  { title: t('core.devtools.routePath'), key: 'path' },
  { title: t('core.devtools.routeName'), dataIndex: 'name', key: 'name', width: 175 },
])

const navigate = async (path = targetPath.value) => {
  if (navigating.value) return
  const candidate = path.trim()
  if (!candidate.startsWith('/') || candidate.startsWith('//')) {
    message.error(t('core.devtools.invalidRoute'))
    return
  }
  const resolved = router.resolve(candidate)
  if (!resolved.matched.length || resolved.path.includes(':')) {
    message.error(t('core.devtools.invalidRoute'))
    return
  }
  navigating.value = true
  try {
    const failure = await router.push(resolved)
    if (failure) message.info(t('core.devtools.navigationCancelled'))
  } catch {
    message.error(t('core.devtools.navigationFailed'))
  } finally {
    navigating.value = false
  }
}
</script>

<template>
  <section class="devtools-section">
    <div class="devtools-toolbar">
      <h3>{{ t('core.devtools.currentRoute') }}</h3>
      <a-button size="small" @click="copyDevtoolsText(route.fullPath)"
        ><CopyOutlined />{{ t('core.devtools.copyPath') }}</a-button
      >
    </div>
    <p class="devtools-code current-path">{{ route.fullPath }}</p>
    <pre class="devtools-code route-json">{{ currentRoute }}</pre>
  </section>
  <a-input-search
    v-model:value="targetPath"
    :placeholder="t('core.devtools.routeInput')"
    :aria-label="t('core.devtools.routeInput')"
    :enter-button="t('core.devtools.navigate')"
    :loading="navigating"
    @search="navigate"
  />
  <section class="devtools-section">
    <h3>{{ t('core.devtools.routeHistory') }}</h3>
    <div class="route-history">
      <div
        v-for="(visit, index) in history.slice(0, 10)"
        :key="`${index}-${visit.fullPath}`"
        class="route-visit"
      >
        <time class="devtools-muted">{{ visit.time }}</time>
        <button class="devtools-route-button" @click="navigate(visit.fullPath)">
          {{ visit.fullPath }}
        </button>
      </div>
    </div>
    <p class="devtools-muted">{{ t('core.devtools.historyHint') }}</p>
  </section>
  <div class="devtools-toolbar">
    <h3>{{ t('core.devtools.registeredRoutes') }}</h3>
    <a-input
      v-model:value="search"
      :placeholder="t('core.devtools.searchRoutes')"
      :aria-label="t('core.devtools.searchRoutes')"
      class="route-search"
      allow-clear
    />
  </div>
  <a-table
    :columns="columns"
    :data-source="registeredRoutes"
    row-key="path"
    size="small"
    :pagination="{ pageSize: 8, showSizeChanger: false }"
  >
    <template #bodyCell="{ column, record }">
      <template v-if="column.key === 'path'">
        <button class="devtools-route-button" @click="targetPath = record.path">
          {{ record.path }}
        </button>
        <span class="devtools-muted">{{ record.title }}</span>
      </template>
      <code v-else class="devtools-code">{{ record.name }}</code>
    </template>
  </a-table>
  <p class="devtools-muted">{{ t('core.devtools.routeHint') }}</p>
</template>

<style scoped>
.current-path {
  color: var(--ant-color-primary);
  margin-bottom: 12px;
}
.route-json {
  padding: 12px;
  border-radius: 6px;
  background: var(--ant-color-fill-quaternary);
}
.route-history {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.route-visit {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  gap: 8px;
}
.route-search {
  max-width: 300px;
}
</style>
