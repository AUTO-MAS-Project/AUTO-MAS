<template>
  <div class="predefined-teams">
    <div
      class="teams-header"
      role="button"
      :aria-expanded="!collapsed"
      @click="collapsed = !collapsed"
    >
      <CaretRightOutlined class="teams-caret" :class="{ expanded: !collapsed }" />
      <span class="teams-title">{{ t('edit.zzzodPredefinedTeams') }}</span>
      <a-tooltip :title="t('edit.zzzodPredefinedTeamsHint')">
        <QuestionCircleOutlined class="teams-help" @click.stop />
      </a-tooltip>
      <a-button
        v-if="!collapsed"
        size="small"
        type="primary"
        class="teams-save"
        :loading="saving"
        :disabled="!dirty"
        @click.stop="saveTeams()"
      >
        {{ t('edit.zzzodTeamsSaveButton') }}
      </a-button>
    </div>

    <a-spin v-show="!collapsed" :spinning="loading">
      <div class="team-list">
        <div v-for="team in teams" :key="team.idx" class="team-block">
          <div class="team-row-top">
            <span class="team-idx">{{ team.idx + 1 }}</span>
            <a-input
              v-model:value="team.name"
              :placeholder="t('edit.zzzodTeamNamePlaceholder')"
              class="team-name-input"
            />
            <span class="team-field-label">{{ t('edit.zzzodTeamBattleConfig') }}</span>
            <a-select
              v-model:value="team.autoBattle"
              :options="autoBattles"
              class="team-auto-select"
              show-search
              option-filter-prop="label"
            />
          </div>
          <div class="team-row-agents">
            <a-select
              v-for="(agent, ai) in team.agents"
              :key="ai"
              v-model:value="team.agents[ai]"
              :options="agentOptions"
              class="team-agent-select"
              show-search
              option-filter-prop="label"
            />
          </div>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CaretRightOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'

interface TeamItem {
  idx: number
  name: string
  autoBattle: string
  agents: string[]
}

const props = defineProps<{
  scriptId: string
  userId: string
  /** 直控模式为所选实例下标；用户模式传 null（写绑定槽） */
  instanceIdx: number | null
}>()

const { t } = useI18n()

// 固定 20 个编队（与一条龙编队页一致）：名称 + 绑定配队方案 + 3 个成员空位
// 可编辑；保存整表写回 team.yml
const teams = ref<TeamItem[]>([])
const autoBattles = ref<{ label: string; value: string }[]>([])
const agentOptions = ref<{ label: string; value: string }[]>([])
const loading = ref(false)
const saving = ref(false)
// 默认折叠，减少显示占用
const collapsed = ref(true)
// 脏状态基线：加载/保存成功后的整表快照，有变更才亮保存按钮
const teamsBaseline = ref('')

const dirty = computed(() => JSON.stringify(teams.value) !== teamsBaseline.value)

const normalizeAgents = (agents: string[] | null | undefined) => {
  // 成员固定 3 个空位（与上游 PredefinedTeamInfo 补齐规则一致）
  const list = (agents ?? []).filter(a => !!a)
  while (list.length < 3) list.push('unknown')
  return list.slice(0, 3)
}

const loadTeams = async () => {
  if (!props.userId) return
  loading.value = true
  try {
    const resp = await Service.getZzzodTeamsApiApiScriptsZzzodTeamsGet(
      props.scriptId,
      props.userId,
      props.instanceIdx
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodTeamsLoadFailed'))
    }
    teams.value = (resp.teams ?? []).map(t => ({
      idx: t.idx,
      name: t.name,
      autoBattle: t.autoBattle,
      agents: normalizeAgents(t.agents),
    }))
    autoBattles.value = (resp.autoBattle ?? []).map(o => ({
      label: String(o.label ?? ''),
      value: String(o.value ?? ''),
    }))
    agentOptions.value = [
      { label: t('edit.zzzodTeamAgentEmpty'), value: 'unknown' },
      ...(resp.agentOptions ?? []).map(o => ({
        label: String(o.label ?? ''),
        value: String(o.value ?? ''),
      })),
    ]
    teamsBaseline.value = JSON.stringify(teams.value)
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodTeamsLoadFailed'))
  } finally {
    loading.value = false
  }
}

/** 整表保存（名称 + 配队方案绑定 + 成员 agent_id_list） */
const saveTeams = async () => {
  if (loading.value || saving.value) return
  saving.value = true
  try {
    const resp = await Service.saveZzzodTeamsApiApiScriptsZzzodTeamsSavePost({
      scriptId: props.scriptId,
      userId: props.userId,
      teams: teams.value.map(t => ({
        name: t.name,
        autoBattle: t.autoBattle,
        agent_id_list: t.agents,
      })),
      instanceIdx: props.instanceIdx ?? undefined,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodTeamsSaveFailed'))
    }
    teamsBaseline.value = JSON.stringify(teams.value)
    message.success(t('edit.zzzodTeamsSaved'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodTeamsSaveFailed'))
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadTeams()
})

// 直控切换所选实例：编队跟随目标位置重载（instanceIdx=null=用户绑定槽）
watch(
  () => props.instanceIdx,
  () => {
    void loadTeams()
  }
)

// 供父级在快速导入等整体覆盖配置的操作后强制刷新
defineExpose({ reload: loadTeams })
</script>

<style scoped>
/* 任务配置卡底部折叠区块 */
.predefined-teams {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.teams-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.teams-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
}

.teams-caret {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  transition: transform 0.2s;
}

.teams-caret.expanded {
  transform: rotate(90deg);
}

.teams-help {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

/* 保存按钮：手动保存（编辑不即时落盘） */
.teams-save {
  margin-left: auto;
}

/* 一行两个编队块 */
.team-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.team-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.team-row-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.team-row-agents {
  display: flex;
  align-items: center;
  gap: 10px;
}

.team-row-agents .team-agent-select {
  flex: 1;
  min-width: 0;
}

.team-idx {
  min-width: 22px;
  text-align: center;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
  flex-shrink: 0;
}

.team-name-input {
  flex: 1;
  min-width: 0;
}

.team-field-label {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

.team-auto-select {
  width: 170px;
  flex-shrink: 0;
}
</style>
