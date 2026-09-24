/**
 * 奇想盒配置来源两态：与后端 ``WhimboxConfigModeValidator`` 的白名单一致。
 *
 * 上游只有一份 config.json 且没有脚本级一条龙配置，「脚本」与「用户」在运行时
 * 行为一致（都写 MAS 面板值），故只保留两态；存量的「用户」由后端自动归一到
 * 「脚本」。页面与 Section 共用本表，避免两处各写一份白名单。
 */
export const WHIMBOX_CONFIG_MODES = ['脚本', '直控'] as const

export type WhimboxConfigMode = (typeof WHIMBOX_CONFIG_MODES)[number]
