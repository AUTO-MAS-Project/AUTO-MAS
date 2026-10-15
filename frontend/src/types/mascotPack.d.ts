export type AppearanceCategory = 'theme' | 'mascot'
export type AppearanceFilter = 'all' | AppearanceCategory

/** 主题附带和独立桌宠共用同一套图片与动画格式。 */
export interface MascotDefinition {
  path: string
  width?: number
  opacity?: number
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
  /** 两行等宽精灵图：第一行待机，第二行工作。 */
  animation?: {
    path: string
    columns: number
    idleFps?: number
    workingFps?: number
    /** 3×3 视线图，按左上到右下排列。 */
    lookPath?: string
    /** 两行结果动画：第一行失败，第二行成功。 */
    resultPath?: string
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
