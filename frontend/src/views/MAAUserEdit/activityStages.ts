// 活动关优先与活动库存保持共用序号解析；调用方先按各自规则筛选列表。
export const resolveActivityStage = <T>(
  stages: readonly T[],
  stageIndex: number | undefined
): T | undefined => {
  if (!stageIndex || stageIndex < 1) return undefined
  return stages[stageIndex - 1] ?? stages[0]
}
