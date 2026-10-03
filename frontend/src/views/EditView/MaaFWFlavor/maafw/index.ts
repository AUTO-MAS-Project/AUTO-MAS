// 通用 MaaFW：任何带 interface.json 的项目都由它运行。其它特调没写的地方都按它来，
// 未知 / 空类型也落到这里。它是默认值本身，所以写全每个字段，不经过 defineMaaFWFlavor。
import type { MaaFWFlavor } from '@/composables/maafwFlavorTypes'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export const MAAFW_FLAVOR: MaaFWFlavor = {
  type: 'MaaFW',
  scriptConfigType: 'MaaFWConfig',
  userConfigType: 'MaaFWUserConfig',
  defaultScriptName: '新 MFW 脚本',
  typeTagLabel: 'MFW',
  typeTagColor: 'geekblue',
  logo: SCRIPT_LOGOS.MaaFW,
  docUrl: MAS_DOC_URLS.scripts,
  routes: {
    suffix: 'maafw',
    // 沿用改成按注册表生成前手写的四个标题，一字不差（「添加 MFW 用户」带空格）
    titles: {
      script: '编辑MFW脚本',
      setup: 'MaaFramework项目引导',
      userAdd: '添加 MFW 用户',
      userEdit: '编辑 MFW 用户',
    },
  },
  create: {
    card: {
      // MaaFW 是通用引擎，不是专项：任何带 interface.json 的项目都由它运行，和「通用脚本」并列。
      titleKey: 'scripts.type.MaaFW',
      descriptionKey: 'scripts.create.typeDesc.MaaFW',
      keywords: ['maafw', 'maaframework', 'framework', 'mfw', 'interface.json', '通用'],
      group: 'general',
      after: 'General',
    },
    sections: {},
    slots: {},
  },
  scriptPage: {
    text: {
      titleKey: null,
      sourceDirectoryKey: 'edit.localProjectDirectory',
      sourceHintKey: 'edit.pickMfwProjectDirectory',
      sourcePlaceholderKey: 'edit.pickActualMfwProject',
    },
    page: null,
    sections: {},
    slots: {},
    prepare: null,
  },
  userPage: {
    text: {
      accountPlaceholderKey: 'edit.localNoteOnly',
      accountTooltipKey: 'edit.maafwAccountRecordTooltip',
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
