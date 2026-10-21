<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { parseStatusTagList } from '@/composables/useStatusTag'
import type { ScriptListItem, ScriptListUser } from '../scriptListModel'
import {
  getConfigSource,
  getOverlayState,
  getMaaEndResourceLabel,
  getMaaEndResourceTagColor,
  getServerTagColor,
  getServerDisplayName,
  getZzzOdModeLabel,
  getZzzOdModeTagColor,
  isZzzOdUserMode,
  getZzzOdRegionLabel,
  getZzzOdAccountValue,
} from '../scriptListPresentation'
const props = defineProps<{
  script: ScriptListItem
  user: ScriptListUser
  accountExpanded: boolean
  passwordExpanded: boolean
}>()
const emit = defineEmits<{
  edit: [user: ScriptListUser]
  delete: [user: ScriptListUser]
  toggleStatus: [user: ScriptListUser]
  toggleDisclosure: [userId: string, kind: 'account' | 'password']
}>()
const { t } = useI18n()
const script = computed(() => props.script),
  user = computed(() => props.user)
const copyAndExpand = async (user: ScriptListUser, kind: 'account' | 'password', value: string) => {
  emit('toggleDisclosure', user.id, kind)
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    message.success(
      t(kind === 'password' ? 'comp.passwordCopiedClipboard' : 'comp.accountCopiedClipboard')
    )
  } catch {
    message.error(t('comp.copyFailed'))
  }
}
const handleUserIdClick = (user: ScriptListUser) =>
  copyAndExpand(user, 'account', user.Info.Id || '')
const handlePasswordClick = (user: ScriptListUser) =>
  copyAndExpand(user, 'password', user.Info.Password || '')
const handleZzzOdAccountClick = (user: ScriptListUser) =>
  copyAndExpand(user, 'account', getZzzOdAccountValue(user))
const handleEditUser = (user: ScriptListUser) => emit('edit', user)
const handleDeleteUser = (user: ScriptListUser) => emit('delete', user)
const handleToggleUserStatus = (user: ScriptListUser) => emit('toggleStatus', user)
// 获取账号ID显示文本
const getUserIdDisplayText = (user: ScriptListUser): string => {
  const userIdValue = user.Info.Id || ''

  if (props.accountExpanded) {
    // 展开状态：显示完整内容或未设置
    return userIdValue ? `账号: ${userIdValue}` : '账号: 未设置'
  } else {
    // 隐藏状态：只显示标题
    return '账号'
  }
}

// 获取密码显示文本
const getPasswordDisplayText = (user: ScriptListUser): string => {
  const passwordValue = user.Info.Password || ''

  if (props.passwordExpanded) {
    // 展开状态：显示完整内容或未设置
    return passwordValue ? `密码: ${passwordValue}` : '密码: 未设置'
  } else {
    // 隐藏状态：只显示标题
    return '密码'
  }
}

const getZzzOdAccountText = (user: ScriptListUser): string => {
  const accountValue = getZzzOdAccountValue(user)
  if (props.accountExpanded) {
    // 展开状态：显示完整账号或未设置
    return accountValue ? `账号: ${accountValue}` : '账号: 未设置'
  }
  // 收起状态：只显示 4 位尾号以压缩卡片内展示宽度（账号本就明文可见，非脱敏）
  return accountValue ? accountValue.slice(-4) : '账号: 未设置'
}
</script>
<template>
  <div :key="user.id" class="user-item">
    <span
      class="user-drag-handle"
      :title="t('comp.dragReorder')"
      :aria-label="t('comp.dragReorder')"
    >
      <span class="script-drag-dots" aria-hidden="true"></span>
    </span>
    <div class="user-info">
      <div class="user-details-row">
        <div class="user-name-section">
          <span class="user-name">{{ user.Info.Name }}</span>
          <!-- MAA、SRC、MaaEnd 和 HSR 脚本显示服务器标签 -->
          <a-tag
            v-if="script.type === 'MAA' || script.type === 'SRC' || script.type === 'MaaEnd'"
            :color="
              script.type === 'MaaEnd'
                ? getMaaEndResourceTagColor(user)
                : getServerTagColor(user.Info.Server)
            "
            class="server-tag"
          >
            {{
              script.type === 'MaaEnd'
                ? getMaaEndResourceLabel(user)
                : getServerDisplayName(user.Info.Server)
            }}
          </a-tag>

          <!-- ZzzOd 脚本显示配置来源标签（独立来源/原生来源） -->
          <a-tag
            v-if="script.type === 'ZzzOd'"
            :color="getZzzOdModeTagColor(user)"
            class="server-tag"
          >
            {{ getZzzOdModeLabel(user) }}
          </a-tag>

          <!-- ZzzOd 独立来源显示区服/账号（原生来源的事实源是一条龙原生配置，MAS 字段会失真，不显示避免歧义） -->
          <template v-if="script.type === 'ZzzOd' && isZzzOdUserMode(user)">
            <a-tag color="blue" class="server-tag">
              {{ getZzzOdRegionLabel(user) }}
            </a-tag>
            <a-tag color="blue" class="clickable-tag" @click="handleZzzOdAccountClick(user)">
              {{ getZzzOdAccountText(user) }}
            </a-tag>
          </template>

          <!-- 账号标签 (HSR 不显示账号/密码) -->
          <a-tag
            v-if="script.type === 'MAA' || script.type === 'SRC' || script.type === 'MaaEnd'"
            :color="script.type === 'MaaEnd' ? 'blue' : getServerTagColor(user.Info.Server)"
            class="clickable-tag"
            @click="handleUserIdClick(user)"
          >
            {{ getUserIdDisplayText(user) }}
          </a-tag>

          <!-- 密码标签 (HSR 不显示账号/密码) -->
          <a-tag
            v-if="script.type === 'MAA' || script.type === 'SRC' || script.type === 'MaaEnd'"
            :color="script.type === 'MaaEnd' ? 'blue' : getServerTagColor(user.Info.Server)"
            class="clickable-tag"
            @click="handlePasswordClick(user)"
          >
            {{ getPasswordDisplayText(user) }}
          </a-tag>

          <!-- 当前配置来源与覆写状态：跟在账号标签之后，与账号名同行左对齐，弱化显示 -->
          <div
            v-if="getConfigSource(script, user)"
            class="user-config-summary"
            :class="{ 'is-overlay-on': getOverlayState(script, user) }"
          >
            <span class="user-config-summary__label">{{
              t('comp.currentConfig', { source: getConfigSource(script, user) })
            }}</span>
            <template v-if="getOverlayState(script, user) !== null">
              <span class="user-config-summary__sep" aria-hidden="true">·</span>
              <span class="user-config-summary__dot" aria-hidden="true"></span>
              {{
                getOverlayState(script, user)
                  ? t('comp.configOverrideEnabled')
                  : t('comp.configOverrideDisabled')
              }}
            </template>
          </div>
        </div>

        <!-- 所有已登记专项共用后端状态标签的显示规则 -->
        <div class="user-info-tags">
          <!-- 直接使用后端提供的Tag字段 -->
          <a-tag
            v-for="(tag, index) in parseStatusTagList(user.Info.Tag)"
            :key="index"
            :title="tag.text"
            :class="['info-tag']"
            :color="tag.color"
          >
            {{ tag.text }}
          </a-tag>
        </div>
      </div>
    </div>

    <div class="user-controls">
      <div class="user-status">
        <a-switch
          :checked="Boolean(user.Info.Status)"
          :checked-children="t('comp.enabled')"
          :un-checked-children="t('comp.disabled')"
          class="status-switch"
          @click="handleToggleUserStatus(user)"
        />
      </div>

      <div class="user-actions">
        <a-tooltip :title="t('comp.editUserConfiguration')">
          <a-button
            type="default"
            size="middle"
            class="user-action-btn"
            @click="handleEditUser(user)"
          >
            <template #icon>
              <EditOutlined />
            </template>
            {{ t('comp.edit') }}
          </a-button>
        </a-tooltip>
        <a-popconfirm
          :title="t('comp.deleteThisUser')"
          :description="t('comp.thisCannotBeUndone')"
          :ok-text="t('comp.ok')"
          :cancel-text="t('comp.cancel')"
          @confirm="handleDeleteUser(user)"
        >
          <a-tooltip :title="t('comp.deleteUser')">
            <a-button type="default" size="middle" danger class="user-action-btn">
              <template #icon>
                <DeleteOutlined />
              </template>
              {{ t('comp.delete') }}
            </a-button>
          </a-tooltip>
        </a-popconfirm>
      </div>
    </div>
  </div>
</template>
<style scoped src="./scriptUserRow.css"></style>
<style scoped src="./scriptListDrag.css"></style>
