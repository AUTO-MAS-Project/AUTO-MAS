// 项目图标（任务、选项、输入字段）解码失败时不显示破图：藏起来，等同于没声明图标。
// 同一个 <img> 会被复用（换选中任务时只换 src），所以换成能加载的图后要再显示回来。

export const hideBrokenMaaFWIcon = (event: Event) => {
  const image = event.currentTarget as HTMLImageElement | null
  if (image) image.style.display = 'none'
}

export const showLoadedMaaFWIcon = (event: Event) => {
  const image = event.currentTarget as HTMLImageElement | null
  if (image) image.style.removeProperty('display')
}
