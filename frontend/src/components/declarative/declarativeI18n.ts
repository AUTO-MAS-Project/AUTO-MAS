import { fallbackLocales, normalizeLocale } from '@/i18n'

export type DeclarativeI18nScope = 'script' | 'user' | 'plan' | 'settings'

const hostKeys: Partial<Record<DeclarativeI18nScope, Record<string, string>>> = {
  script: {
    'Info.label': 'core.edit.basicInfo',
    'Info.Name.label': 'core.edit.scriptName',
    'Info.Path.label': 'core.edit.mainProgramPath',
    'Run.label': 'core.edit.runConfiguration',
    'Run.GameUpdateTimeLimit.label': 'core.edit.gameUpdateTimeoutMinutes',
    'Run.GameUpdateTimeLimit.tip': 'core.edit.timeoutDownloadingInstallingGame',
    'Run.HardTimeLimit.label': 'core.edit.hardTimeoutMinutes',
    'Run.HardTimeLimit.tip': 'core.edit.hardTimeoutHint',
    'Run.IfAutoInstallGameApk.label': 'core.edit.installGamePackageAutomatically',
    'Run.IfAutoInstallGameApk.tip': 'core.edit.whenClientDetectedAs',
    'Run.IfCheckGameUpdate.label': 'core.edit.checkGameUpdateBefore',
    'Run.IfCheckGameUpdate.tip': 'core.edit.checkGameUpdateBeforeLogin',
    'Run.ProxyTimesLimit.label': 'core.edit.runsPerDayThis',
    'Run.ProxyTimesLimit.tip': 'core.edit.skipRunOnceThis',
    'Run.RunTimeLimit.label': 'core.edit.runTimeoutMinutes2',
    'Run.RunTimeLimit.tip': 'core.edit.treatRunAsTimed',
    'Run.RunTimesLimit.label': 'core.edit.retryLimit',
    'Run.RunTimesLimit.tip': 'core.edit.ifRunStillUnfinished',
    'Run.TaskTransitionMethod.label': 'core.edit.taskTransitionMethod',
    'Run.TaskTransitionMethod.options.NoAction': 'core.scheduler.power.noAction',
    'Run.TaskTransitionMethod.options.ExitGame': 'core.edit.restartGame',
    'Run.TaskTransitionMethod.options.ExitEmulator': 'core.edit.restartEmulator',
    'Update.label': 'core.edit.updateTakeover',
    'Update.TakeoverEnabled.label': 'core.edit.updateTakeoverSwitch',
    'Update.PackageMode.label': 'core.edit.updatePackageMode',
    'Update.PackageMode.options.full': 'core.edit.updatePackageFull',
    'Update.PackageMode.options.incremental': 'core.edit.updatePackageIncremental',
    'Update.Channel.label': 'core.edit.updateChannel',
    'Update.Channel.options.stable': 'core.edit.maafwUpdateChannelStable',
    'Update.Channel.options.beta': 'core.edit.maafwUpdateChannelBeta',
    'Update.MirrorChyanCDK.label': 'core.edit.updateTakeoverCdk',
  },
  user: {
    'Info.label': 'core.edit.basicInfo',
    'Info.Base.label': 'core.edit.configurationSource',
    'Info.Base.tip': 'core.edit.configSourceHintBase',
    'Info.Base.options.shared': 'core.edit.script',
    'Info.Base.options.independent': 'core.edit.user',
    'Info.Base.options.native': 'core.edit.directControl',
    'Info.Id.label': 'core.edit.accountId',
    'Info.IfQuickConfig.label': 'core.edit.enableQuickConfiguration',
    'Info.IfScriptAfterTask.label': 'core.comp.runScriptAfterTask',
    'Info.IfScriptAfterTask.tip': 'core.comp.runCustomScriptAfter',
    'Info.IfScriptBeforeTask.label': 'core.comp.runScriptBeforeTask',
    'Info.IfScriptBeforeTask.tip': 'core.comp.runCustomScriptBefore',
    'Info.Name.label': 'core.edit.username',
    'Info.Notes.label': 'core.edit.note',
    'Info.Password.label': 'core.edit.password',
    'Info.RemainedDay.label': 'core.edit.daysLeft',
    'Info.RemainedDay.tip': 'core.edit.daysLeftAccount1',
    'Info.ScriptAfterTask.label': 'core.comp.runScriptAfterTask',
    'Info.ScriptBeforeTask.label': 'core.comp.runScriptBeforeTask',
    'Info.Server.label': 'core.edit.server',
    'Info.Status.label': 'core.edit.enabled',
    'Info.Status.options.on': 'core.edit.enabled3',
    'Info.Status.options.off': 'core.edit.disabled',
    'Info.Tag.label': 'core.edit.baahUserTag',
    'Notify.label': 'core.edit.notificationSettings',
    'Notify.Enabled.label': 'core.edit.enableNotifications',
    'Notify.IfSendMail.label': 'core.edit.emailNotification',
    'Notify.IfSendStatistic.label': 'core.edit.statistics',
    'Notify.IfServerChan.label': 'core.edit.serverchan',
    'Notify.ServerChanKey.label': 'core.setting.notify.serverChanKey',
    'Notify.ServerChanKey.tip': 'core.setting.notify.serverChanKeyTip',
    'Notify.ToAddress.label': 'core.edit.recipient',
    'Notify.IfNotifyRecruit.label': 'core.edit.notifyRecruit',
    'Notify.IfNotifyDropStatistics.label': 'core.edit.notifyDropStatistics',
    'Notify.PushLogMode.label': 'core.edit.collectNodeDetails',
    'Notify.PushLogMode.tip': 'core.edit.collectsKeyMomentsFrom',
    'Notify.PushLogMode.options.关闭': 'core.edit.pushLogModeOff',
    'Notify.PushLogMode.options.逐条': 'core.edit.pushLogModeList',
    'Notify.PushLogMode.options.汇总': 'core.edit.pushLogModeSummary',
    'Stage.label': 'core.edit.stageConfiguration',
  },
}

export function createDeclarativeI18n(
  t: (key: string, params: Record<string, unknown>, options: { locale: string }) => string,
  te: (key: string, locale: string) => boolean,
  locale: string,
  namespace: string,
  scope: DeclarativeI18nScope
) {
  const locales = new Set([locale, ...fallbackLocales(normalizeLocale(locale))])
  const plugin = /^(plugins\..+)\.config$/.exec(namespace)?.[1]

  function resolve(keys: (string | undefined)[], params: Record<string, unknown> = {}) {
    for (const loc of locales) {
      const key = keys.find(key => key && te(key, loc))
      if (key) return t(key, params, { locale: loc })
    }
  }

  function config(path: string | string[], params?: Record<string, unknown>) {
    const common = hostKeys[scope]
    const keys = [path].flat().flatMap(subpath => {
      const group = /^([^.]+)\.label$/.exec(subpath)?.[1]
      return [
        plugin && `${plugin}.${scope}.config.${subpath}`,
        namespace && `${namespace}.${subpath}`,
        // 兼容以分组名直接存放标题的插件词表。
        namespace && group && `${namespace}.${group}`,
        common && Object.prototype.hasOwnProperty.call(common, subpath)
          ? common[subpath]
          : undefined,
      ]
    })
    return resolve(keys, params)
  }

  return {
    config,
    panel(key: string, params?: Record<string, unknown>) {
      return resolve([plugin && `${plugin}.${key}`], params)
    },
    tip(group: string, hint: { field?: string; description?: string | null }) {
      return config(`${group}.${hint.field}.tip`) ?? hint.description ?? ''
    },
  }
}
