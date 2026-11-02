// 主题包和默认主题共用 4px 网格，容器圆角由控件圆角加内边距得到。
export const normalizeRadius = (radius = 8): number => Math.max(4, Math.round(radius / 4) * 4)

export const createRadiusTheme = (radius?: number) => {
  const control = normalizeRadius(radius)
  return {
    token: {
      borderRadius: control,
      borderRadiusSM: control,
      borderRadiusXS: 4,
      borderRadiusLG: control,
      borderRadiusOuter: 4,
    },
    components: {
      Card: { borderRadiusLG: control + 24 },
      Modal: { borderRadiusLG: control + 24, paddingMD: 24 },
      Tag: { borderRadiusSM: 4 },
    },
  }
}
