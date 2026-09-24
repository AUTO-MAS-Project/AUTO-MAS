// 服务器枚举 → 展示名（脚本页用户行、计划表活动关指派共用）。
// 中文词表与编辑页服务器下拉同口径，未收录的值原样返回。

/** 获取服务器显示名称；未知值回退原文，空值显示「未知」 */
export const getServerDisplayName = (server: string): string => {
  switch (server) {
    // MAA服务器
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
    // SRC服务器
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
