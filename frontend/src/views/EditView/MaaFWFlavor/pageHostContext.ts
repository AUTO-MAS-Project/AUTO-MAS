// 页面宿主（MaaFWPageHost）交给页面的上下文。单独成文件：页面的编排层要取它，而宿主模块
// 会按需引入页面，放在一起就成环了。
import { hasInjectionContext, inject, type InjectionKey, type Ref } from 'vue'
import type { MaaFWPageKind } from '@/composables/maafwFlavorTypes'
import type { ScriptDetail, ScriptType } from '@/types/script'

export interface MaaFWPageHostContext {
  /**
   * 脚本当前类型：宿主按它选渲染哪个页面。页面读到（或导入后重新读到）脚本详情时写回这里，
   * 类型变了宿主就地换页面（都是默认页时组件不变，页面不重建）。
   */
  scriptType: Ref<ScriptType>
  /** 页面种类（路由 meta.maafwPage）：脚本页看它是不是引导 */
  mode: MaaFWPageKind
  /** 引导当前步骤：放在宿主里，换页面后新页面接着这一步走 */
  wizardStep: Ref<number>
  /**
   * 宿主已经读到的脚本详情，只交给第一个来取的页面（之后返回 undefined）：
   * - 脚本详情：直接用，不再请求一次；
   * - null：读过了但没读到（脚本不存在或读取失败，getScript 已经提示过），按页面现有的报错处理；
   * - undefined：宿主没有可交的，页面自己去读。
   */
  takeInitialScript: () => ScriptDetail | null | undefined
}

export const MAAFW_PAGE_HOST_KEY: InjectionKey<MaaFWPageHostContext> = Symbol('MaaFWPageHost')

/** 页面里取宿主上下文；不在宿主里（单测直接调编排层）时为 null，页面按自己读路由的老办法走 */
export const useMaaFWPageHostContext = (): MaaFWPageHostContext | null =>
  hasInjectionContext() ? inject(MAAFW_PAGE_HOST_KEY, null) : null
