// 一条龙内置配置组（与后端 BetterGIUserConfig.OneDragon.Groups 的默认项保持一致）。
// value 参与后端判定，保持中文原样；只有显示名接词表。
// 顺序为 MAS 默认一条龙顺序（体力作战插在「自动幽境危战」之前，见 initDragonList）：
// 领取邮件 → 领取尘歌壶奖励 → 合成树脂 → 自动幽境危战 → 自动地脉花 → 自动首领讨伐 → 自动秘境 → 领取每日奖励
export const ONE_DRAGON_GROUPS = [
  { value: '领取邮件', labelKey: 'edit.bettergiGroupMail' },
  { value: '领取尘歌壶奖励', labelKey: 'edit.bettergiGroupTeapot' },
  { value: '合成树脂', labelKey: 'edit.bettergiGroupResin' },
  { value: '自动幽境危战', labelKey: 'edit.bettergiGroupStygian' },
  { value: '自动地脉花', labelKey: 'edit.bettergiGroupLeyLine' },
  { value: '自动首领讨伐', labelKey: 'edit.bettergiGroupBoss' },
  { value: '自动秘境', labelKey: 'edit.bettergiGroupDomain' },
  { value: '领取每日奖励', labelKey: 'edit.bettergiGroupDailyReward' },
]

// ============================================================
// 一条龙配置组「队列可视化」（8 内置 + 体力作战 + 自定义组）
// ============================================================
// 交互语义：
//  - 左栏列表即「一条龙队列」：其中的配置组按顺序执行。默认顺序 =
//    领取邮件 → 合成树脂 → 体力作战 → 自动幽境危战 → 自动地脉花 → 自动首领讨伐 → 自动秘境 → 领取尘歌壶奖励 → 领取每日奖励。
//  - 行前缀 tag：内置 →「默认」；体力作战 →「专项」；自定义组 →「自定义」。
//  - 行内胶囊开关控制是否启用（内置 ↔ Groups；自定义 ↔ CustomGroups；体力作战为本地虚拟项）。
//  - 点击「添加配置组」：从候选（8 内置 + 体力作战 + BetterGI 现有自定义组）挑选，加入队列末尾。
//  - 右键某一配置组：从一条龙移除（内置移出 Groups、自定义移出 CustomGroups、体力作战移除并关闭）。
//  - 体力作战启用互斥：开启体力作战时，自动关闭并冻结「自动秘境 / 自动地脉花 / 自动首领讨伐」；
//    体力作战关闭或从一条龙移除后才解冻，三组可重新开启。
// 说明：队列顺序与成员（含重复实例）持久化在 OneDragon.Queue（JSON 数组，元素
// {kind, name}），运行时后端按队列顺序重建一条龙 TaskOrder；行启停仍由
// Groups / CustomGroups 承载，体力作战为本地虚拟项不落库。
export const STAMINA_COMBAT_KEY = '__mas_stamina_combat__'

export type ConfigGroupKind =
  | 'builtin'
  | 'stamina'
  | 'custom'
  | 'js'
  | 'pathing'
  | 'scriptgroup'
  | 'keymouse'

export type ConfigGroupIdentity = {
  kind: ConfigGroupKind
  key: string // builtin/custom/js/pathing: 组名字面量或相对路径；stamina: STAMINA_COMBAT_KEY
  /** 前名（配置组名称）：仅前端展示的组级别名，不进入 key、不影响运行；留空按来源类型回退默认名 */
  displayName?: string
  /** 后名（后缀别名）：仅作显示用，不进入 key；执行仍按 key（前名/基名）归一。留空即旧式「自动秘境」 */
  suffix?: string
  /** 队列行唯一实例标识：允许同一配置组重复添加时，每行都有独立 uid（拖拽/删除按行实例） */
  uid?: number
  /** 每实例独立启用状态：战斗 4 项走执行层 Plan，按此启停；其余组不使用此字段 */
  enabled?: boolean
  /**
   * 绑定的执行层 Plan 步骤 uid：同名多实例（如「自动秘境」×3）靠它定向排序——
   * 后端 build_combat_steps 按 planUid 精确匹配 Plan 步骤，队列拖拽顺序才能逐实例生效。
   * 由 persistDragonQueue 按行实例的 Plan 步骤名（stepNameIn）自动解析写入。
   */
  planUid?: string
}

// 启用体力作战时自动关闭并冻结的官方内置组（专项接管刷取）
export const STAMINA_FROZEN_BUILTINS = ['自动秘境', '自动地脉花', '自动首领讨伐', '自动幽境危战']

// 重复添加配置组功能开关：开启后允许同一配置组在一条龙中多次添加（每行为独立实例）。
// 后端"同一配置多次添加"的语义后续详说，本开关用于先行测试。
export const ALLOW_DUPLICATE_GROUPS = true

// 「体力作战」专项暂未开展制作：功能开关保持关闭，队列与添加面板均不展示该虚拟项，
// 避免误导用户（待专项完成后置 true 即可恢复，相关逻辑保留在后文）。
export const STAMINA_COMBAT_VISIBLE = false

// 前缀 tag 颜色（队列行/右栏详情/候选弹窗统一走同一套）：默认=灰、专项=紫、配置组=橘、
// 脚本&JS=蓝、路径=绿、配置组=橙、录制=绯红
export const kindTagClass = (kind: ConfigGroupKind): string => {
  if (kind === 'stamina') return 'gi-kind-tag-stamina'
  if (kind === 'pathing') return 'gi-kind-tag-pathing'
  if (kind === 'scriptgroup') return 'gi-kind-tag-scriptgroup'
  if (kind === 'keymouse') return 'gi-kind-tag-keymouse'
  if (kind === 'custom' || kind === 'js') return 'gi-kind-tag-custom'
  return 'gi-kind-tag-default'
}

// 地图追踪相对路径（不含 .json）→ 展示文件名（取路径最后一段）
export const pathingDisplayName = (rel: string): string => {
  const seg = String(rel || '')
    .split('/')
    .filter(Boolean)
    .pop()
  return seg || rel
}
