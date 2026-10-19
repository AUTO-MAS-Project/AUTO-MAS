export type AppearanceCategory = 'theme' | 'mascot'
export type AppearanceFilter = 'all' | AppearanceCategory

/** 菜单 UI 由包声明，能力标识及状态由宿主解释。 */
export interface MascotMenuDefinition {
  protocolVersion: 1
  layout: 'list' | 'grid'
  items: Array<{ capability: string; icon?: string } | { separator: true }>
  style?: {
    width?: number
    radius?: number
    fontSize?: number
    itemHeight?: number
    background?: string
    text?: string
    border?: string
    accent?: string
  }
}

/** 主题附带和独立桌宠共用同一套图片与动画格式。 */
export interface MascotDefinition {
  path: string
  width?: number
  opacity?: number
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
  menu?: MascotMenuDefinition
  /** 等宽精灵图：上半部分待机，下半部分工作，各动作按行排列。 */
  animation?: {
    path: string
    columns: number
    /** 每个动作的帧数，最多 120；省略时等于 columns，兼容旧包。 */
    frameCount?: number
    idleFps?: number
    workingFps?: number
    /** 3×3 视线图，按左上到右下排列。 */
    lookPath?: string
    /** 结果动画：上半部分失败，下半部分成功，排布与主动画一致。 */
    resultPath?: string
    /** 拖拽动画，列数和帧数与主动画一致，仅含一个动作。 */
    dragPath?: string
  }
}

export interface MascotManifest {
  formatVersion: 1
  id: string
  name: string
  description?: string
  mascot: MascotDefinition
  preview?: string
}

export interface MascotAssets {
  mascot?: MascotDefinition
  mascotUrl?: string
  mascotAnimationUrl?: string
  mascotLookUrl?: string
  mascotResultUrl?: string
  mascotDragUrl?: string
}

export interface InstalledMascot extends MascotManifest, MascotAssets {
  mascot: MascotDefinition
  previewUrl?: string
}

export interface MascotImportResult {
  success: boolean
  mascot?: MascotSummary
  existing?: MascotSummary
  code?: 'INVALID_PACKAGE' | 'INVALID_ANIMATION' | 'DUPLICATE_ID' | 'IMPORT_FAILED'
  error?: string
}

/** 列表只带缩略图，精灵图留在主进程按需读取。 */
export type MascotSummary = Pick<InstalledMascot, 'id' | 'name' | 'description' | 'previewUrl'>
