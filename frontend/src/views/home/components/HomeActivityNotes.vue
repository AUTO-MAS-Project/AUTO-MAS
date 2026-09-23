<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import type { HomeModuleKey } from '@/types/home'
import { useCommunityActivityStore } from '@/stores/communityActivity'
import {
  useCommunityActivityApi,
  type ActivitySnapshot,
} from '@/views/gamesign/useCommunityActivityApi'
import type { PlatformResult } from '@/views/gamesign/gameSignDisplay'
import { activityNoteKey, activityNoteGameName } from '../activityNote'
import { useHomeActivityNoteSelection } from '../useHomeActivityNoteSelection'
import { collectGameSignUsers, summarizeGameSign } from '../signStats'
import HomeSignSummary from './HomeSignSummary.vue'
import HomeActivityNoteStrip from './HomeActivityNoteStrip.vue'

defineOptions({
  name: 'HomeActivityNotes',
})

const props = defineProps<{
  /** 当前轮播游戏键；签到情况与便笺长条都跟随它切换 */
  activeKey: HomeModuleKey | null
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('首页社区信息')
const { querySignResult } = useCommunityActivityApi()
const activityStore = useCommunityActivityStore()
const { snapshots, loading, errorMessage: activityError } = storeToRefs(activityStore)

const signLoading = ref(false)
const signError = ref(false)

/** 最近一次签到结果快照；首页只读展示，签到动作仍发生在游戏社区页 */
const signResult = ref<PlatformResult>({})

const loadSignResult = async () => {
  signLoading.value = true
  signError.value = false
  try {
    signResult.value = await querySignResult()
  } catch (error) {
    signError.value = true
    logger.warn(`读取签到结果失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    signLoading.value = false
  }
}

const refresh = () => {
  void activityStore.load()
  void loadSignResult()
}

/** 合并当前游戏的签到记录与便笺账号；两者都没有数据时返回 null。 */
const signSummary = computed(() => {
  const gameName = activityNoteGameName(props.activeKey)
  return gameName === null ? null : summarizeGameSign(signResult.value, gameName, snapshots.value)
})

const signUsers = computed(() => {
  const gameName = activityNoteGameName(props.activeKey)
  return gameName === null ? [] : collectGameSignUsers(signResult.value, gameName, snapshots.value)
})

const { notes, selectedNote, selectNote } = useHomeActivityNoteSelection(
  snapshots,
  computed(() => props.activeKey)
)
const noteLabel = (snapshot: ActivitySnapshot) =>
  [
    snapshot.account || t('gamesign.unknownUser'),
    snapshot.roleName !== snapshot.account ? snapshot.roleName : '',
    snapshot.server,
    snapshot.roleUid ? t('gamesign.activity.roleUid', { uid: snapshot.roleUid }) : '',
  ]
    .filter(Boolean)
    .join(' · ')
const noteOptions = computed(() =>
  notes.value.map(snapshot => ({
    value: activityNoteKey(snapshot),
    label: noteLabel(snapshot),
  }))
)

/** 签到情况与日常便笺都没有该游戏的数据时，整块不展示 */
const hasCommunityData = computed(() => Boolean(signSummary.value) || Boolean(selectedNote.value))
const supportsNotes = computed(() => Boolean(activityNoteGameName(props.activeKey)))
const showNoteFeedback = computed(
  () =>
    supportsNotes.value && ((loading.value && !selectedNote.value) || Boolean(activityError.value))
)

onMounted(() => {
  void activityStore.load()
  void loadSignResult()
})
</script>

<template>
  <section
    v-if="hasCommunityData || showNoteFeedback"
    class="home-activity-notes"
    :aria-label="t('home.activityNotes.title')"
  >
    <HomeSignSummary
      v-if="signSummary"
      class="notes-daily"
      :class="{ 'is-standalone': !selectedNote && !showNoteFeedback }"
      :game-key="activeKey"
      :summary="signSummary"
      :users="signUsers"
      :loading="signLoading || loading"
      :error="signError"
      :show-refresh="!selectedNote && !showNoteFeedback"
      @refresh="refresh"
    />

    <!-- 日常便笺（宽）：当前游戏的便笺长条 -->
    <div v-if="selectedNote || showNoteFeedback" class="notes-memos">
      <div v-if="showNoteFeedback" class="note-feedback" role="status">
        <a-spin v-if="loading" size="small" />
        <span>{{
          loading ? t('home.activityNotes.loading') : t('gamesign.activity.queryFailed')
        }}</span>
        <span v-if="!loading" class="notes-daily-hint">{{ activityError }}</span>
        <a-button v-if="!loading" type="link" size="small" @click="refresh">{{
          t('gamesign.activity.refresh')
        }}</a-button>
      </div>
      <HomeActivityNoteStrip
        v-if="selectedNote"
        :snapshot="selectedNote"
        :loading="loading || signLoading"
        @refresh="refresh"
      >
        <template #identity>
          <a-select
            v-if="notes.length > 1"
            class="note-user-select"
            size="small"
            show-search
            option-filter-prop="label"
            :value="activityNoteKey(selectedNote)"
            :options="noteOptions"
            :aria-label="t('home.activityNotes.selectUser')"
            :title="noteLabel(selectedNote)"
            @change="selectNote(String($event))"
          />
          <span v-else :title="noteLabel(selectedNote)">{{ noteLabel(selectedNote) }}</span>
        </template>
      </HomeActivityNoteStrip>
    </div>
  </section>
</template>

<style scoped>
/* 吸顶由轮播统一承载，确保游戏导航始终在社区信息上方。 */
.home-activity-notes {
  display: flex;
  align-items: stretch;
  gap: 12px;
  padding: 8px 12px;
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
}

/* 日常情况占一小列 */
.notes-daily {
  flex: 0 0 280px;
  max-width: 40%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding: 4px 12px 4px 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  border-right: 1px solid var(--ant-color-border-secondary);
}

.notes-daily-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
/* 只有日常情况、没有便笺时让它占满整行，避免左侧一条细块 */
.notes-daily.is-standalone {
  flex: 1;
  max-width: none;
  border-right: none;
}

/* 日常便笺占大部分宽度 */
.notes-memos {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.note-feedback {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 48px;
  color: var(--ant-color-text-secondary);
}

.note-user-select {
  width: 100%;
  max-width: 280px;
}

@media (max-width: 800px) {
  /* 窄屏时「日常情况」与「日常便笺」改成上下堆叠 */
  .home-activity-notes {
    flex-direction: column;
    align-items: stretch;
  }

  .notes-daily {
    flex: 0 0 auto;
    max-width: none;
    border-right: none;
    border-bottom: 1px solid var(--ant-color-border-secondary);
    padding-bottom: 8px;
  }
}
</style>
