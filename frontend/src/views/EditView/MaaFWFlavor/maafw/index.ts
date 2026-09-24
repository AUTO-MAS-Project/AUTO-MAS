// 通用 MaaFW：任何带 interface.json 的项目都由它运行。其它特调没写的地方都按它来，
// 未知 / 空类型也落到这里。
import type { MaaFWFlavor } from '@/composables/maafwFlavorTypes'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export const MAAFW_FLAVOR: MaaFWFlavor = {
  type: 'MaaFW',
  scriptConfigType: 'MaaFWConfig',
  userConfigType: 'MaaFWUserConfig',
  routeSuffix: 'maafw',
  defaultScriptName: '新 MFW 脚本',
  typeTagLabel: 'MFW',
  typeTagColor: 'geekblue',
  logo: SCRIPT_LOGOS.MaaFW,
  docUrl: MAS_DOC_URLS.scripts,
  createOption: {
    // MaaFW 是通用引擎，不是专项：任何带 interface.json 的项目都由它运行，和「通用脚本」并列。
    titleKey: 'scripts.type.MaaFW',
    descriptionKey: 'scripts.create.typeDesc.MaaFW',
    keywords: ['maafw', 'maaframework', 'framework', 'mfw', 'interface.json', '通用'],
    group: 'general',
    after: 'General',
  },
  scriptTitleKey: null,
  sourceDirectoryKey: 'edit.localProjectDirectory',
  sourceHintKey: 'edit.pickMfwProjectDirectory',
  sourcePlaceholderKey: 'edit.pickActualMfwProject',
  controllerHintKey: null,
  accountPlaceholderKey: 'edit.localNoteOnly',
  accountTooltipKey: 'edit.maafwAccountRecordTooltip',
  queueHintKey: null,
  slots: {},
  prepareUserPage: null,
}
