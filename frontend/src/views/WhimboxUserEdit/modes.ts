/**
 * 奇想盒配置来源三态：与后端 ``UserDirectConfigModeValidator`` 的白名单一致。
 *
 * 语义按 #879（base ⊕ overlay）：三态只是 base 的磁盘 owner——「脚本/用户」=
 * 共享/独立 base（本页面板值，当前运行行为一致：都物化本页值），为后续特殊功能
 * 预留；「直控」=原生 base（奇想盒自带配置，MAS 零写入，开启覆写层时任务前
 * 物化面板覆盖集、结束还原）。页面与 Section 共用本表，避免两处各写一份白名单。
 */
export const WHIMBOX_CONFIG_MODES = ['脚本', '用户', '直控'] as const

export type WhimboxConfigMode = (typeof WHIMBOX_CONFIG_MODES)[number]
