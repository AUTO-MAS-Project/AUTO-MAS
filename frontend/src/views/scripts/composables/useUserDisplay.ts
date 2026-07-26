// useUserDisplay.ts - 脚本用户行显示辅助逻辑
// 提取自 ScriptTable.vue：用户标签、账号/密码显隐、服务器配色等纯展示逻辑。
// 状态仅包含本组件内部的展开/收起标记，不涉及业务流程或 API 调用。

import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { parseStatusTagList, type StatusTag } from '@/composables/useStatusTag'

const getInfoFieldValue = (user: any, field: string): any => user?.Info?.[field]

const hasInfoField = (user: any, field: string): boolean => {
  const info = user?.Info
  return !!info && Object.prototype.hasOwnProperty.call(info, field)
}

const hasInfoDisplayValue = (user: any, field: string): boolean => {
  const value = getInfoFieldValue(user, field)
  return value !== undefined && value !== null && String(value).length > 0
}

const getValueByPath = (source: Record<string, any> | null | undefined, path: string): unknown => {
  if (!source || !path) return undefined
  return path.split('.').reduce<unknown>((current, key) => {
    if (!current || typeof current !== 'object') return undefined
    return (current as Record<string, unknown>)[key]
  }, source)
}

const getSchemaFields = (schema: any): any[] => {
  if (!schema) return []
  if (Array.isArray(schema.groups)) {
    return schema.groups.flatMap((group: any) => (Array.isArray(group.fields) ? group.fields : []))
  }
  if (typeof schema === 'object') {
    return Object.entries(schema).map(([key, field]) => ({
      ...(field && typeof field === 'object' ? field : {}),
      key,
    }))
  }
  return []
}

export const getUserStatusTags = (user: any): StatusTag[] => {
  const tagFields = getSchemaFields(user?.schema).filter(field => field?.type === 'tag')
  const tags = tagFields.flatMap(field =>
    parseStatusTagList(getValueByPath(user?.config || user, field.key || field.name || ''))
  )
  return tags.length > 0 ? tags : parseStatusTagList(user?.Info?.Tag)
}

export const isPassCheckTag = (tag: StatusTag): boolean => tag.text === '人工排查未通过'

export const shouldShowServerTag = (user: any): boolean =>
  hasInfoDisplayValue(user, 'Server') || hasInfoDisplayValue(user, 'Resource')

export const shouldShowUserIdTag = (user: any): boolean => hasInfoDisplayValue(user, 'Id')

export const shouldShowPasswordTag = (user: any): boolean => hasInfoField(user, 'Password')

export const shouldShowStatusTags = (user: any): boolean => getUserStatusTags(user).length > 0

const getMaaEndResourceLabel = (user: any): string => user.Info?.Resource || '官服'

const getMaaEndResourceTagColor = (): string => 'blue'

export const getServerTagColor = (server: string): string => {
  switch (server) {
    case 'Official':
      return 'blue'
    case 'Bilibili':
      return 'purple'
    case 'YoStarEN':
      return 'green'
    case 'YoStarJP':
      return 'red'
    case 'YoStarKR':
      return 'orange'
    case 'txwy':
      return 'gold'
    case 'CN-Official':
      return 'blue'
    case 'CN-Bilibili':
      return 'purple'
    case 'VN-Official':
      return 'cyan'
    case 'OVERSEA-America':
      return 'green'
    case 'OVERSEA-Asia':
      return 'orange'
    case 'OVERSEA-Europe':
      return 'geekblue'
    case 'OVERSEA-TWHKMO':
      return 'gold'
    default:
      return 'gray'
  }
}

export const getServerDisplayName = (server: string): string => {
  switch (server) {
    case 'Official':
      return '官服'
    case 'Bilibili':
      return 'B服'
    case 'YoStarEN':
      return '国际服'
    case 'YoStarJP':
      return '日服'
    case 'YoStarKR':
      return '韩服'
    case 'txwy':
      return '繁中服'
    case 'CN-Official':
      return '官服'
    case 'CN-Bilibili':
      return 'B服'
    case 'VN-Official':
      return '越南服'
    case 'OVERSEA-America':
      return '美服'
    case 'OVERSEA-Asia':
      return '亚服'
    case 'OVERSEA-Europe':
      return '欧服'
    case 'OVERSEA-TWHKMO':
      return '港澳台服'
    default:
      return server || '未知'
  }
}

export const getUserServerTagColor = (user: any): string => {
  const server = getInfoFieldValue(user, 'Server')
  if (server !== undefined && server !== null && String(server).length > 0) {
    return getServerTagColor(String(server))
  }
  return getMaaEndResourceTagColor()
}

export const getUserServerDisplayName = (user: any): string => {
  const server = getInfoFieldValue(user, 'Server')
  if (server !== undefined && server !== null && String(server).length > 0) {
    return getServerDisplayName(String(server))
  }
  return getMaaEndResourceLabel(user)
}

export const getUserIdentityTagColor = (user: any): string => {
  const server = getInfoFieldValue(user, 'Server')
  if (server !== undefined && server !== null && String(server).length > 0) {
    return getServerTagColor(String(server))
  }
  return getMaaEndResourceTagColor()
}

export interface UserDisplayHandle {
  expandedUserIds: ReturnType<typeof ref<Set<string>>>
  expandedUserPasswords: ReturnType<typeof ref<Set<string>>>
  handleUserIdClick: (user: any) => Promise<void>
  handlePasswordClick: (user: any) => Promise<void>
  getUserIdDisplayText: (user: any) => string
  getPasswordDisplayText: (user: any) => string
}

export function useUserDisplay(): UserDisplayHandle {
  const expandedUserIds = ref<Set<string>>(new Set())
  const expandedUserPasswords = ref<Set<string>>(new Set())

  const handleUserIdClick = async (user: any) => {
    const userId = user.id
    const userIdValue = user.Info.Id || ''
    if (expandedUserIds.value.has(userId)) {
      expandedUserIds.value.delete(userId)
    } else {
      expandedUserIds.value.add(userId)
    }
    if (userIdValue) {
      try {
        await navigator.clipboard.writeText(userIdValue)
        message.success('账号已复制到剪贴板')
      } catch {
        message.error('复制失败')
      }
    }
  }

  const handlePasswordClick = async (user: any) => {
    const userId = user.id
    const passwordValue = user.Info.Password || ''
    if (expandedUserPasswords.value.has(userId)) {
      expandedUserPasswords.value.delete(userId)
    } else {
      expandedUserPasswords.value.add(userId)
    }
    if (passwordValue) {
      try {
        await navigator.clipboard.writeText(passwordValue)
        message.success('密码已复制到剪贴板')
      } catch {
        message.error('复制失败')
      }
    }
  }

  const getUserIdDisplayText = (user: any): string => {
    const userId = user.id
    const userIdValue = user.Info.Id || ''
    if (expandedUserIds.value.has(userId)) {
      return userIdValue ? `账号: ${userIdValue}` : '账号: 未设置'
    }
    return '账号'
  }

  const getPasswordDisplayText = (user: any): string => {
    const userId = user.id
    const passwordValue = user.Info.Password || ''
    if (expandedUserPasswords.value.has(userId)) {
      return passwordValue ? `密码: ${passwordValue}` : '密码: 未设置'
    }
    return '密码'
  }

  return {
    expandedUserIds,
    expandedUserPasswords,
    handleUserIdClick,
    handlePasswordClick,
    getUserIdDisplayText,
    getPasswordDisplayText,
  }
}
