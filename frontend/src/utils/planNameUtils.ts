/**
 * 计划表名称管理工具函数
 */

import { getPlanTypeDescriptor } from './planTypeRegistry'

export interface PlanNameValidationResult {
  isValid: boolean
  /** 词表 key，由调用方解析 */
  messageKey?: string
}

/**
 * 生成唯一的计划表名称（使用数字后缀）
 * @param planType 计划表类型
 * @param existingNames 已存在的名称列表
 * @returns 唯一的计划表名称
 */
export function generateUniquePlanName(planType: string, existingNames: string[]): string {
  const baseName = getPlanTypeDescriptor(planType)?.defaultName || '新计划表'

  // 如果基础名称没有被使用，直接返回
  if (!existingNames.includes(baseName)) {
    return baseName
  }

  // 查找可用的编号
  let counter = 2
  let candidateName = `${baseName} ${counter}`

  while (existingNames.includes(candidateName)) {
    counter++
    candidateName = `${baseName} ${counter}`
  }

  return candidateName
}

/**
 * 验证计划表名称是否可用
 * @param newName 新名称
 * @param existingNames 已存在的名称列表
 * @param currentName 当前名称（编辑时排除自己）
 * @returns 验证结果
 */
export function validatePlanName(
  newName: string,
  existingNames: string[],
  currentName?: string
): PlanNameValidationResult {
  // 检查名称是否为空
  if (!newName || !newName.trim()) {
    return { isValid: false, messageKey: 'plan.toast.nameEmpty' }
  }

  const trimmedName = newName.trim()

  // 检查名称长度
  if (trimmedName.length > 50) {
    return { isValid: false, messageKey: 'plan.toast.nameTooLong' }
  }

  // 检查是否与其他计划表重名（排除当前名称）
  const isDuplicate = existingNames.some(name => name === trimmedName && name !== currentName)

  if (isDuplicate) {
    return { isValid: false, messageKey: 'plan.toast.nameDuplicate' }
  }

  return { isValid: true }
}

/**
 * 获取计划表类型显示标签的词表 key
 * @param planType 计划表类型
 * @returns 词表 key
 */
export function getPlanTypeLabelKey(planType: string): string {
  return getPlanTypeDescriptor(planType)?.displayNameKey || 'plan.typeFallback'
}
