// 通用 MaaFW：任何带 interface.json 的项目都由它运行。其它特调没写的地方都按它来，
// 未知 / 空类型也落到这里。它是默认值本身，所以写全每个字段，不经过 defineMaaFWFlavor。
import type { MaaFWFlavor } from '@/composables/maafwFlavorTypes'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'

const metadata = SCRIPT_METADATA.MaaFW

export const MAAFW_FLAVOR: MaaFWFlavor = {
  type: 'MaaFW',
  scriptConfigType: 'MaaFWConfig',
  userConfigType: 'MaaFWUserConfig',
  defaultScriptName: '新 MFW 脚本',
  typeTagLabel: metadata.label,
  typeTagColor: metadata.typeTagColor,
  logo: metadata.logo,
  docUrl: MAS_DOC_URLS.scripts,
  routes: {
    suffix: metadata.routeSuffix,
    // 沿用改成按注册表生成前手写的四个标题，一字不差（「添加 MFW 用户」带空格）
    titles: {
      ...metadata.routeTitles,
      setup: 'MaaFramework项目引导',
    },
  },
  create: {
    card: {
      // MaaFW 是通用引擎，不是专项：任何带 interface.json 的项目都由它运行，和「通用脚本」并列。
      ...metadata.create,
      after: 'General',
    },
    sections: {},
    slots: {},
  },
  scriptPage: {
    text: {
      titleKey: null,
      sourceDirectoryKey: 'core.edit.localProjectDirectory',
      sourceHintKey: 'core.edit.pickMfwProjectDirectory',
      sourcePlaceholderKey: 'core.edit.pickActualMfwProject',
    },
    page: null,
    sections: {},
    slots: {},
    prepare: null,
  },
  userPage: {
    text: {
      accountPlaceholderKey: 'core.edit.localNoteOnly',
      accountTooltipKey: 'core.edit.maafwAccountRecordTooltip',
      queueHintKey: null,
    },
    managed: {
      entries: [],
      accountTask: null,
      warningKey: null,
      noticeKey: null,
    },
    page: null,
    sections: {},
    slots: {},
    prepare: null,
  },
}
