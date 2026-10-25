<script setup lang="ts">
import { computed } from 'vue'
import {
  CopyOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  EllipsisOutlined,
  SettingOutlined,
  UpOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import type { ScriptListItem } from '../scriptListModel'
import { isMaaFWFamily, resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import {
  getScriptLogo,
  getScriptLogoAlt,
  isMaaEndPresetSupported,
  getScriptTypeLabel,
  getScriptTypeTagColor,
} from '../scriptListPresentation'
const props = defineProps<{
  script: ScriptListItem
  configuring: boolean
  collapsed: boolean
  searching?: boolean
  copyingScriptId?: string | null
}>()
const emit = defineEmits<{
  action: [action: ScriptCardAction, script: ScriptListItem]
  toggleUsers: [scriptId: string]
}>()
const script = computed(() => props.script)
const handleStartMAAConfig = (script: ScriptListItem) => emit('action', 'startMaaConfig', script)
const handleStartSRCConfig = (script: ScriptListItem) => emit('action', 'startSrcConfig', script)
const handleStartMaaEndConfig = (script: ScriptListItem) =>
  emit('action', 'startMaaEndConfig', script)
const handleStartOkwwConfig = (script: ScriptListItem) => emit('action', 'startOkwwConfig', script)
const handleStartWhimboxConfig = (script: ScriptListItem) =>
  emit('action', 'startWhimboxConfig', script)
const handleEdit = (script: ScriptListItem) => emit('action', 'edit', script)
const handleAddUser = (script: ScriptListItem) => emit('action', 'addUser', script)
const handleCopy = (script: ScriptListItem) => emit('action', 'copy', script)
const handleDeleteConfirm = (script: ScriptListItem) => emit('action', 'delete', script)
</script>
<script lang="ts">
export type ScriptCardAction =
  | 'startMaaConfig'
  | 'startSrcConfig'
  | 'startMaaEndConfig'
  | 'startOkwwConfig'
  | 'startWhimboxConfig'
  | 'edit'
  | 'addUser'
  | 'copy'
  | 'delete'
</script>
<template>
  <div class="script-header">
    <div class="script-info">
      <span
        class="script-drag-handle"
        :title="$t('comp.dragReorder')"
        :aria-label="$t('comp.dragReorder')"
      >
        <span class="script-drag-dots" aria-hidden="true"></span>
      </span>
      <div class="script-logo-container">
        <img
          v-if="isMaaFWFamily(script.type)"
          :src="resolveMaaFWFlavor(script.type).logo"
          :alt="resolveMaaFWFlavor(script.type).typeTagLabel"
          class="script-logo"
        />
        <img
          v-else
          :src="getScriptLogo(script.type)"
          :alt="getScriptLogoAlt(script.type)"
          class="script-logo"
        />
      </div>
      <div class="script-details">
        <h3 class="script-name">{{ script.name }}</h3>
        <a-tag :color="getScriptTypeTagColor(script.type)" class="script-type">
          {{ getScriptTypeLabel(script) }}
        </a-tag>
      </div>
    </div>
    <div class="header-actions">
      <a-button
        v-if="script.type === 'MAA' && !props.configuring"
        type="primary"
        ghost
        size="middle"
        @click="handleStartMAAConfig(script)"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configureMaa') }}
      </a-button>
      <a-button
        v-if="script.type === 'MAA' && props.configuring"
        type="default"
        size="middle"
        disabled
        style="color: #52c41a; border-color: #52c41a"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configuring') }}
      </a-button>
      <a-button
        v-if="script.type === 'SRC' && !props.configuring"
        type="primary"
        ghost
        size="middle"
        @click="handleStartSRCConfig(script)"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configureSrc') }}
      </a-button>
      <a-button
        v-if="script.type === 'SRC' && props.configuring"
        type="default"
        size="middle"
        disabled
        style="color: #52c41a; border-color: #52c41a"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configuring') }}
      </a-button>
      <a-button
        v-if="isMaaEndPresetSupported(script) && !props.configuring"
        type="primary"
        ghost
        size="middle"
        @click="handleStartMaaEndConfig(script)"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configureMaaend') }}
      </a-button>
      <a-button
        v-if="isMaaEndPresetSupported(script) && props.configuring"
        type="default"
        size="middle"
        disabled
        style="color: #52c41a; border-color: #52c41a"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configuring') }}
      </a-button>
      <a-button
        v-if="script.type === 'Okww' && !props.configuring"
        type="primary"
        ghost
        size="middle"
        @click="handleStartOkwwConfig(script)"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configureOkWw') }}
      </a-button>
      <a-button
        v-if="script.type === 'Okww' && props.configuring"
        type="default"
        size="middle"
        disabled
        style="color: #52c41a; border-color: #52c41a"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configuring') }}
      </a-button>
      <a-button
        v-if="script.type === 'Whimbox' && !props.configuring"
        type="primary"
        ghost
        size="middle"
        @click="handleStartWhimboxConfig(script)"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configureWhimbox') }}
      </a-button>
      <a-button
        v-if="script.type === 'Whimbox' && props.configuring"
        type="default"
        size="middle"
        disabled
        style="color: #52c41a; border-color: #52c41a"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ $t('comp.configuring') }}
      </a-button>
      <a-button type="default" size="middle" @click="handleEdit(script)">
        <template #icon>
          <EditOutlined />
        </template>
        {{ $t('comp.editScript') }}
      </a-button>
      <a-button
        type="default"
        size="middle"
        class="action-button add-button"
        @click="handleAddUser(script)"
      >
        <template #icon>
          <UserAddOutlined />
        </template>
        {{ $t('comp.addUser') }}
      </a-button>
      <a-dropdown :trigger="['click']">
        <a-button
          size="middle"
          class="action-button"
          :loading="props.copyingScriptId === script.id"
          :disabled="Boolean(props.copyingScriptId)"
        >
          <template #icon>
            <EllipsisOutlined />
          </template>
          {{ $t('comp.more') }}
        </a-button>
        <template #overlay>
          <a-menu>
            <a-menu-item key="copy" @click="handleCopy(script)">
              <CopyOutlined />
              {{ $t('comp.copyScript') }}
            </a-menu-item>
            <a-menu-divider />
            <a-menu-item key="delete" danger @click="handleDeleteConfirm(script)">
              <DeleteOutlined />
              {{ $t('comp.deleteScript') }}
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
      <a-tooltip
        :title="
          props.searching
            ? $t('comp.expandUsersWhileSearching')
            : props.collapsed
              ? $t('comp.expandUsers')
              : $t('comp.collapseUsers')
        "
      >
        <a-button
          size="middle"
          class="action-button"
          :disabled="props.searching"
          :aria-label="props.collapsed ? $t('comp.expandUsers') : $t('comp.collapseUsers')"
          @click="emit('toggleUsers', script.id)"
        >
          <template #icon>
            <DownOutlined v-if="props.collapsed" />
            <UpOutlined v-else />
          </template>
        </a-button>
      </a-tooltip>
    </div>
  </div>
</template>
<style scoped src="./scriptCardHeader.css"></style>
<style scoped src="./scriptListDrag.css"></style>
