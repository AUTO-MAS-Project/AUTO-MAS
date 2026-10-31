<template>
  <div class="operator-card" :class="{ 'operator-card-collapsed': collapsed }">
    <!-- 头部：勾选 + 名称/职业/星级 + 目标摘要（折叠时也能看清培养内容） -->
    <div class="operator-head">
      <a-checkbox
        class="operator-select"
        :checked="selected"
        :disabled="busy"
        :aria-label="t('core.edit.maaCultivateSelectOperator', { name: view.name })"
        @change="emit('toggle-selection', view.operatorId, $event.target.checked)"
      />
      <button
        type="button"
        class="operator-toggle"
        :aria-label="t('core.edit.maaCultivateToggleGoals')"
        :aria-expanded="!collapsed"
        @click="emit('toggle-collapse', view.operatorId)"
      >
        <DownOutlined aria-hidden="true" :class="{ 'toggle-icon-collapsed': collapsed }" />
      </button>
      <span
        class="operator-name"
        :title="view.name"
        @click="emit('toggle-collapse', view.operatorId)"
        >{{ view.name }}</span
      >
      <a-tag v-if="view.profession" class="operator-profession">{{ view.profession }}</a-tag>
      <span v-if="view.rarity > 0" class="operator-rarity" :aria-label="`${view.rarity}★`">{{
        '★'.repeat(Math.min(view.rarity, 6))
      }}</span>
      <span class="operator-summary" :title="view.summary">{{ view.summary }}</span>
      <a-tooltip v-if="view.overLimit" :title="t('core.edit.maaCultivateOverLimit')">
        <a-tag color="warning" class="operator-over-limit">
          {{ t('core.edit.maaCultivateOverLimitShort') }}
        </a-tag>
      </a-tooltip>
      <a-button
        class="operator-remove"
        size="small"
        danger
        :disabled="busy"
        @click="emit('remove', view.operatorId)"
      >
        {{ t('core.edit.maaCultivateRemove') }}
      </a-button>
    </div>
    <!-- 目标组：精英化/技能等级单行直出，专精/模组带组标题；达成行不给下拉
         （静态档位），后端下次注入会自动移除 -->
    <div v-show="!collapsed" class="operator-body">
      <template v-for="group in view.groups" :key="group.kind">
        <div v-if="isItemGroup(group)" class="goal-group">
          <div class="goal-group-title">
            <span>{{ group.label }}</span>
            <a-tooltip v-if="group.hint" :title="group.hint">
              <QuestionCircleOutlined aria-hidden="true" class="goal-group-hint" />
            </a-tooltip>
          </div>
          <div v-for="line in group.lines" :key="line.key" class="goal-row">
            <span class="goal-name" :title="line.label">{{ line.label }}</span>
            <CultivateGoalLineBody
              :line="line"
              :disabled="busy || !sklandBound"
              :get-popup-container="getPopupContainer"
              :list-height="listHeight"
              @change="
                level => emit('goal-change', view.operatorId, line.kind, line.targetId, level)
              "
            />
          </div>
        </div>
        <template v-else>
          <div v-for="line in group.lines" :key="line.key" class="goal-row goal-row-plain">
            <span class="goal-name" :title="line.label">{{ line.label }}</span>
            <CultivateGoalLineBody
              :line="line"
              :disabled="busy || (line.kind === 'skill' && !sklandBound)"
              :get-popup-container="getPopupContainer"
              :list-height="listHeight"
              @change="
                level => emit('goal-change', view.operatorId, line.kind, line.targetId, level)
              "
            />
          </div>
        </template>
      </template>
      <NoData
        v-if="!view.groups.length"
        class="goal-empty"
        :description="t('core.maaCopilot.noPendingGoals')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { DownOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { usePlanSelectPopup } from './usePlanSelectPopup'
import type { CultivateGoalGroup, CultivateOperatorView } from './cultivateGoalLines'
import CultivateGoalLineBody from './CultivateGoalLineBody.vue'

defineProps<{
  view: CultivateOperatorView
  selected: boolean
  collapsed: boolean
  busy: boolean
  /** 未绑定森空岛时技能/专精/模组目标只读（精英化不受限） */
  sklandBound: boolean
}>()

const emit = defineEmits<{
  'toggle-selection': [operatorId: string, checked: boolean]
  'toggle-collapse': [operatorId: string]
  remove: [operatorId: string]
  'goal-change': [
    operatorId: string,
    kind: CultivateGoalGroup['kind'],
    targetId: string,
    level: unknown,
  ]
}>()

const { t } = useI18n()
const { getPopupContainer, listHeight } = usePlanSelectPopup()

const isItemGroup = (group: CultivateGoalGroup) =>
  group.kind === 'mastery' || group.kind === 'module'
</script>

<style scoped>
.operator-card {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: border-color 0.2s;
}

.operator-card:hover {
  border-color: var(--ant-color-border);
}

.operator-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  min-width: 0;
}

.operator-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--ant-color-text-secondary);
  cursor: pointer;
}

.operator-toggle:hover {
  color: var(--ant-color-text);
}

.operator-toggle :deep(svg) {
  transition: transform 0.2s;
}

.toggle-icon-collapsed {
  transform: rotate(-90deg);
}

.operator-name {
  flex-shrink: 0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: var(--ant-color-text);
  cursor: pointer;
}

.operator-profession {
  flex-shrink: 0;
  margin-inline-end: 0;
}

.operator-rarity {
  flex-shrink: 0;
  font-size: 12px;
  letter-spacing: 1px;
  color: var(--ant-color-text-tertiary);
  white-space: nowrap;
}

/* 摘要吸收余量（超长省略号），把操作按钮钉在行尾 */
.operator-summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  text-align: right;
}

.operator-over-limit {
  flex-shrink: 0;
  margin-inline-end: 0;
  cursor: help;
}

.operator-remove {
  flex-shrink: 0;
}

/* 正文左缩进与头部干员名对齐（勾选 16 + 箭头 22 + 两个间距 8 + 内边距 12） */
.operator-body {
  padding: 6px 12px 10px 54px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.goal-group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.goal-group-title:first-child {
  margin-top: 2px;
}

.goal-group-hint {
  color: var(--ant-color-text-quaternary);
  font-size: 12px;
}

.goal-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  min-width: 0;
}

.goal-row-plain .goal-name {
  font-weight: 500;
}

.goal-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ant-color-text);
}

.goal-empty {
  padding: 8px 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
