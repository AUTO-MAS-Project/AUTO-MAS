/**
 * 计划表名称管理工具函数
 */

export interface PlanNameValidationResult {
  isValid: boolean
  message?: string
}

/**
 * 生成唯一的计划表名称（使用数字后缀）
 * @param planType 计划表类型
 * @param existingNames 已存在的名称列表
 * @returns 唯一的计划表名称
 */
export function generateUniquePlanName(planType: string, existingNames: string[]): string {
  const baseNames = {
    MaaPlanConfig: '新 MAA 计划表',
    GeneralPlan: '新通用计划表',
    CustomPlan: '新自定义计划表',
  } as Record<string, string>
  
  const baseName = baseNames[planType] || '新计划表'
  
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
    return { isValid: false, message: '计划表名称不能为空' }
  }
  
  const trimmedName = newName.trim()
  
  // 检查名称长度
  if (trimmedName.length > 50) {
    return { isValid: false, message: '计划表名称不能超过50个字符' }
  }
  
  // 检查是否与其他计划表重名（排除当前名称）
  const isDuplicate = existingNames.some(name => 
    name === trimmedName && name !== currentName
  )
  
  if (isDuplicate) {
    return { isValid: false, message: '计划表名称已存在，请使用其他名称' }
  }
  
  return { isValid: true }
}

/**
 * 获取计划表类型的显示标签
 * @param planType 计划表类型
 * @returns 显示标签
 */
export function getPlanTypeLabel(planType: string): string {
  const labels = {
    MaaPlanConfig: 'MAA计划表',
    GeneralPlan: '通用计划表',
    CustomPlan: '自定义计划表',
  } as Record<string, string>
  
  return labels[planType] || '计划表'
}