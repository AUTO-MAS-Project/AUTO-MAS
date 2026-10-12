/**
 * 奇想盒配置来源三态：与后端 ``BaseSourceValidator`` 的白名单一致。
 *
 * 语义按 #879（base ⊕ overlay）：三态只是 base 的磁盘 owner——shared/independent
 * 都是本页面板值（当前运行行为一致：都物化本页值），为后续特殊功能预留；
 * native = 原生 base（奇想盒自带配置，MAS 零写入，开启覆写层时任务前
 * 物化面板覆盖集、结束还原）。页面与 Section 共用本表，避免两处各写一份白名单。
 */
export const WHIMBOX_CONFIG_MODES = ['shared', 'independent', 'native'] as const

export type WhimboxConfigMode = (typeof WHIMBOX_CONFIG_MODES)[number]
