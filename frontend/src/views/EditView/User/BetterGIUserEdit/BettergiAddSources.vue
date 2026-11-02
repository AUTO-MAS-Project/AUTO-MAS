<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  ALLOW_DUPLICATE_GROUPS,
  kindTagClass,
  pathingDisplayName,
  type ConfigGroupIdentity,
} from './bettergiQueueIdentity'
import type { useBettergiCatalogs } from './useBettergiCatalogs'
const props = defineProps<{
  catalogs: ReturnType<typeof useBettergiCatalogs>
  editable: boolean
  groupMode: boolean
  candidates: ConfigGroupIdentity[]
  groupCandidates: ConfigGroupIdentity[]
  keyMouseCandidates: ConfigGroupIdentity[]
  groupLabel: (item: ConfigGroupIdentity) => string
  groupPrefix: (item: ConfigGroupIdentity) => string
  isGroupFrozen: (item: ConfigGroupIdentity) => boolean
  inDragon: (item: ConfigGroupIdentity) => boolean
  isChipAdded: (item: ConfigGroupIdentity) => boolean
}>()
const { groupLabel, groupPrefix, isGroupFrozen, inDragon, isChipAdded } = props
const { pathingTreeData, selectedPathingKey, selectedPathingFiles } = props.catalogs
const activeTab = defineModel<string>('activeTab', { required: true })
const emit = defineEmits<{ pick: [item: ConfigGroupIdentity] }>()
const groupsEditable = computed(() => props.editable)
const { t } = useI18n()
const pickAddCandidate = (item: ConfigGroupIdentity) => {
  if (props.editable) emit('pick', item)
}
// 候选中该项已在一条龙时的提示（替代模板内联 message）
const warnAlreadyInDragon = () => {
  message.info(t('core.edit.bettergiAlreadyInDragon'))
}

// 候选是否不可添加：重复开关关闭且已在队列，或被体力作战冻结的刷取内置组
const isCandidateBlocked = (candidate: ConfigGroupIdentity): boolean =>
  (!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)) || isGroupFrozen(candidate)

// 候选点击：冻结组给出冻结提示；已在队列（重复开关关闭时）提示已加入；其余填入输入框。
// 多选：Ctrl=逐个追加当前项；Shift=从锚点（上次普通/Ctrl 点击）到当前项的整段候选追加输入框。
const handleListCandidateClick = (
  list: ConfigGroupIdentity[],
  anchor: { value: number },
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) => {
  if (isGroupFrozen(candidate)) {
    message.warning(t('core.edit.bettergiGroupFrozenTip'))
    return
  }
  if (!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)) {
    warnAlreadyInDragon()
    return
  }
  if (event.shiftKey) {
    // Shift 区间选择：跳过区间内已在气泡中的项，避免与普通点击/Ctrl 点击造成首项重复添加
    const base = anchor.value >= 0 ? anchor.value : index
    const lo = Math.min(base, index)
    const hi = Math.max(base, index)
    for (let i = lo; i <= hi; i += 1) {
      const item = list[i]
      if (item && !isGroupFrozen(item) && !isChipAdded(item)) pickAddCandidate(item)
    }
    return
  }
  anchor.value = index
  pickAddCandidate(candidate)
}

// JS脚本 标签页：自定义组 + JS 脚本候选点击
const handleCandidateClick = (candidate: ConfigGroupIdentity, index: number, event: MouseEvent) =>
  handleListCandidateClick(props.candidates, jsCandidateAnchor, candidate, index, event)

// 配置组 标签页：默认/专项/ScriptGroup 候选点击
const handleGroupCandidateClick = (
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) => handleListCandidateClick(props.groupCandidates, groupCandidateAnchor, candidate, index, event)

// 录制 标签页：KeyMouseScript 候选点击
const handleKeyMouseCandidateClick = (
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) =>
  handleListCandidateClick(
    props.keyMouseCandidates,
    keyMouseCandidateAnchor,
    candidate,
    index,
    event
  )

// JS 候选项 Shift 区间锚点（index in props.candidates）
const jsCandidateAnchor = ref(-1)

// 配置组 候选项 Shift 区间锚点（index in props.groupCandidates）
const groupCandidateAnchor = ref(-1)

// 录制 候选项 Shift 区间锚点（index in props.keyMouseCandidates）
const keyMouseCandidateAnchor = ref(-1)

// 地图追踪文件行 Shift 区间锚点（index in selectedPathingFiles）
const pathingFileAnchor = ref(-1)
const resetAnchors = () => {
  jsCandidateAnchor.value = -1
  groupCandidateAnchor.value = -1
  keyMouseCandidateAnchor.value = -1
  pathingFileAnchor.value = -1
}
defineExpose({ resetAnchors })

const handlePathingSelect = (keys: (string | number)[]) => {
  const first = keys[0]
  selectedPathingKey.value = first != null ? String(first) : ''
  // 目录切换后右侧文件列表变化，重置 Shift 区间锚点
  pathingFileAnchor.value = -1
}

// 点击右表某路径文件：直接生成一个「路径」气泡（同文件多次点击=多个独立实例）
const pickPathingFile = (file: string) => {
  if (!groupsEditable.value) return
  pickAddCandidate({ kind: 'pathing', key: file })
}

// 地图文件行点击：普通=填入当前文件；Ctrl=逐个；Shift=从锚点区间批量填入输入框
const handlePathingFileClick = (file: string, index: number, event: MouseEvent) => {
  if (!groupsEditable.value) return
  if (event.shiftKey) {
    const anchor = pathingFileAnchor.value >= 0 ? pathingFileAnchor.value : index
    const lo = Math.min(anchor, index)
    const hi = Math.max(anchor, index)
    for (let i = lo; i <= hi; i += 1) {
      const item = selectedPathingFiles.value[i]
      if (item && !isChipAdded({ kind: 'pathing', key: item })) pickPathingFile(item)
    }
    return
  }
  pathingFileAnchor.value = index
  pickPathingFile(file)
}
</script>
<template>
  <a-tabs v-model:activeKey="activeTab" size="small">
    <!-- Tab1：配置组（默认内置 + 专项体力 + BetterGI User/ScriptGroup 内容）→ 配置组模式冻结 -->
    <a-tab-pane
      key="scriptgroup"
      :tab="t('core.edit.bettergiTabScriptGroup')"
      :disabled="props.groupMode"
    >
      <div v-if="!props.groupCandidates.length" class="add-dragon-candidates-empty">
        <NoData :description="t('core.edit.bettergiScriptGroupEmptyDir')" />
      </div>
      <div v-else class="add-dragon-candidates">
        <div
          v-for="(candidate, index) in props.groupCandidates"
          :key="`${candidate.kind}:${candidate.key}`"
          class="add-dragon-candidate"
          :class="{
            'add-dragon-candidate-picked': isChipAdded(candidate),
            'add-dragon-candidate-disabled': isCandidateBlocked(candidate),
          }"
          @click="handleGroupCandidateClick(candidate, index, $event)"
        >
          <a-tag
            size="small"
            class="add-dragon-candidate-tag"
            :class="kindTagClass(candidate.kind)"
          >
            {{ groupPrefix(candidate) }}
          </a-tag>
          <span class="add-dragon-candidate-label">{{ groupLabel(candidate) }}</span>
          <a-tag v-if="isGroupFrozen(candidate)" color="orange" size="small">
            {{ t('core.edit.bettergiGroupFrozen') }}
          </a-tag>
          <a-tag
            v-else-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)"
            color="default"
            size="small"
          >
            {{ t('core.edit.bettergiInQueue') }}
          </a-tag>
        </div>
      </div>
    </a-tab-pane>

    <!-- Tab2：JS脚本（JS 脚本 / 自定义组候选） -->
    <a-tab-pane key="js" :tab="t('core.edit.bettergiTabJsScript')">
      <div v-if="!props.candidates.length" class="add-dragon-candidates-empty">
        <NoData :description="t('core.edit.bettergiTabJsEmpty')" />
      </div>
      <div v-else class="add-dragon-candidates">
        <div
          v-for="(candidate, index) in props.candidates"
          :key="`${candidate.kind}:${candidate.key}`"
          class="add-dragon-candidate"
          :class="{
            'add-dragon-candidate-picked': isChipAdded(candidate),
            'add-dragon-candidate-disabled': isCandidateBlocked(candidate),
          }"
          @click="handleCandidateClick(candidate, index, $event)"
        >
          <a-tag
            size="small"
            class="add-dragon-candidate-tag"
            :class="kindTagClass(candidate.kind)"
          >
            {{ groupPrefix(candidate) }}
          </a-tag>
          <span class="add-dragon-candidate-label">{{ groupLabel(candidate) }}</span>
          <a-tag v-if="isGroupFrozen(candidate)" color="orange" size="small">
            {{ t('core.edit.bettergiGroupFrozen') }}
          </a-tag>
          <a-tag
            v-else-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)"
            color="default"
            size="small"
          >
            {{ t('core.edit.bettergiInQueue') }}
          </a-tag>
        </div>
      </div>
    </a-tab-pane>

    <!-- Tab4：录制（KeyMouseScript 键鼠脚本） -->
    <a-tab-pane key="keymouse" :tab="t('core.edit.bettergiTabKeyMouse')">
      <div v-if="!props.keyMouseCandidates.length" class="add-dragon-candidates-empty">
        <NoData :description="t('core.edit.bettergiKeyMouseEmptyDir')" />
      </div>
      <div v-else class="add-dragon-candidates">
        <div
          v-for="(candidate, index) in props.keyMouseCandidates"
          :key="`${candidate.kind}:${candidate.key}`"
          class="add-dragon-candidate"
          :class="{
            'add-dragon-candidate-picked': isChipAdded(candidate),
            'add-dragon-candidate-disabled': isCandidateBlocked(candidate),
          }"
          @click="handleKeyMouseCandidateClick(candidate, index, $event)"
        >
          <a-tag
            size="small"
            class="add-dragon-candidate-tag"
            :class="kindTagClass(candidate.kind)"
          >
            {{ groupPrefix(candidate) }}
          </a-tag>
          <span class="add-dragon-candidate-label">{{ groupLabel(candidate) }}</span>
          <a-tag v-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)" color="default" size="small">
            {{ t('core.edit.bettergiInQueue') }}
          </a-tag>
        </div>
      </div>
    </a-tab-pane>

    <!-- Tab3：地图追踪（AutoPathing 左树右表） -->
    <a-tab-pane key="pathing" :tab="t('core.edit.bettergiTabPathing')" :force-render="true">
      <p class="add-dragon-pathing-hint">{{ t('core.edit.bettergiPathingSelectHint') }}</p>
      <div class="add-dragon-pathing-layout">
        <a-tree
          v-if="pathingTreeData.length"
          class="add-dragon-pathing-tree"
          :tree-data="pathingTreeData"
          :default-expanded-keys="[pathingTreeData[0]?.key]"
          :selected-keys="[selectedPathingKey]"
          @select="handlePathingSelect"
        />
        <div v-else class="add-dragon-pathing-empty">
          <NoData :description="t('core.edit.bettergiPathingEmptyTree')" />
        </div>
        <div class="add-dragon-pathing-files">
          <template v-if="selectedPathingFiles.length">
            <div
              v-for="(file, index) in selectedPathingFiles"
              :key="file"
              class="add-dragon-pathing-file"
              @click="handlePathingFileClick(file, index, $event)"
            >
              <span class="add-dragon-pathing-file-name">{{ pathingDisplayName(file) }}</span>
              <a-tag size="small" :class="kindTagClass('pathing')">
                {{ t('core.edit.bettergiGroupKindPathing') }}
              </a-tag>
            </div>
          </template>
          <div v-else class="add-dragon-pathing-empty">
            <NoData :description="t('core.edit.bettergiPathingEmptyDir')" />
          </div>
        </div>
      </div>
    </a-tab-pane>
  </a-tabs>
</template>
<style scoped>
@import './bettergiGroupTags.css';
.add-dragon-candidates-empty {
  border: 1px dashed var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 24px 12px;
}

.add-dragon-pathing-hint {
  margin: 0 0 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.add-dragon-pathing-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 12px;
  min-height: 220px;
}

.add-dragon-pathing-tree {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.add-dragon-pathing-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.add-dragon-pathing-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.add-dragon-pathing-file:hover {
  background: var(--ant-color-fill-tertiary);
}

.add-dragon-pathing-file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-dragon-pathing-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.add-dragon-candidates {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 10px;
}

.add-dragon-candidate {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 16px;
  background: var(--ant-color-bg-container);
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.add-dragon-candidate:hover {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-fill-tertiary);
}

.add-dragon-candidate-picked {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.add-dragon-candidate-disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.add-dragon-candidate-disabled:hover {
  border-color: var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.add-dragon-candidate-tag {
  flex: 0 0 auto;
  margin-inline-end: 0;
}

.add-dragon-candidate-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
