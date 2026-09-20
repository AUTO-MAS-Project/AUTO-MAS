<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReloadOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { usePerformanceStore } from '@/stores/performance'
import { useCommunityActivityApi, type ActivitySnapshot } from './useCommunityActivityApi'
import CommunityActivityCard from './components/CommunityActivityCard.vue'

const { t, locale } = useI18n()
const performanceStore = usePerformanceStore()
const snapshots = ref<ActivitySnapshot[]>([])
const loading = ref(false)
const hasLoaded = ref(false)
const errorMessage = ref('')
const lastUpdated = ref('')
let requestId = 0
let activityRequest: Promise<void> | null = null

const { queryActivity } = useCommunityActivityApi()

const formatTime = (value: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(locale.value, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

const snapshotKey = (snapshot: ActivitySnapshot) =>
  [snapshot.accountUid, snapshot.platform, snapshot.game, snapshot.roleUid, snapshot.roleName]
    .map(value => value || '-')
    .join(':')

const loadActivity = () => {
  if (activityRequest) return activityRequest

  const currentRequestId = ++requestId
  loading.value = true
  errorMessage.value = ''
  const request = (async () => {
    try {
      const data = await queryActivity()
      if (currentRequestId !== requestId) return

      snapshots.value = data
      const updatedValues = data
        .map(snapshot => snapshot.updatedAt)
        .filter(Boolean)
        .sort()
      lastUpdated.value = updatedValues.at(-1) || new Date().toISOString()
    } catch (error) {
      if (currentRequestId !== requestId) return
      errorMessage.value =
        error instanceof Error ? error.message : t('gamesign.activity.queryFailed')
    } finally {
      if (currentRequestId === requestId) {
        hasLoaded.value = true
        loading.value = false
      }
    }
  })()
  activityRequest = request
  void request.then(
    () => {
      if (activityRequest === request) activityRequest = null
    },
    () => {
      if (activityRequest === request) activityRequest = null
    }
  )
  return request
}

const isEmpty = computed(() => hasLoaded.value && snapshots.value.length === 0)

onMounted(() => {
  void loadActivity()
})
</script>

<template>
  <section class="activity-view" :aria-label="t('gamesign.activity.title')">
    <header class="activity-toolbar">
      <div class="activity-heading">
        <h2 class="activity-title">{{ t('gamesign.activity.title') }}</h2>
        <span v-if="lastUpdated" class="activity-updated">
          {{
            t('gamesign.activity.queriedAt', {
              time: formatTime(lastUpdated),
            })
          }}
        </span>
      </div>
      <a-tooltip :title="t('gamesign.activity.refresh')">
        <a-button
          type="text"
          shape="circle"
          :loading="loading"
          :aria-label="t('gamesign.activity.refresh')"
          @click="loadActivity"
        >
          <ReloadOutlined />
        </a-button>
      </a-tooltip>
    </header>

    <a-alert
      v-if="errorMessage"
      type="error"
      show-icon
      :message="errorMessage"
      class="activity-alert"
    />

    <div v-if="loading && !hasLoaded" class="activity-state">
      <a-spin size="large" />
    </div>

    <a-empty
      v-else-if="isEmpty"
      :description="t('gamesign.activity.empty')"
      class="activity-state"
    />

    <a-spin v-else-if="snapshots.length" :spinning="loading" class="activity-spin">
      <draggable
        v-model="snapshots"
        :item-key="snapshotKey"
        :animation="performanceStore.isLowPower ? 0 : 180"
        handle=".activity-drag-handle"
        ghost-class="activity-card-ghost"
        chosen-class="activity-card-chosen"
        class="activity-grid"
      >
        <template #item="{ element }">
          <article class="activity-card-wrap">
            <CommunityActivityCard
              :snapshot="element"
              :simplified="performanceStore.lowPerformanceMode"
            />
          </article>
        </template>
      </draggable>
    </a-spin>
  </section>
</template>

<style scoped>
.activity-view {
  min-height: 100%;
  box-sizing: border-box;
  padding: 8px 12px;
  color: var(--ant-color-text);
}

.activity-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.activity-heading {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.activity-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
}

.activity-updated,
.activity-muted {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.activity-alert {
  margin-bottom: 6px;
}

.activity-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}

.activity-spin {
  display: block;
}

.activity-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: 8px;
  min-width: 0;
}

.activity-card-wrap {
  min-width: 0;
  min-height: 0;
}

.activity-card-ghost {
  opacity: 0.45;
}

.activity-card-chosen {
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

@media (max-width: 860px) {
  .activity-view {
    padding: 8px;
  }

  .activity-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }

  .activity-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
