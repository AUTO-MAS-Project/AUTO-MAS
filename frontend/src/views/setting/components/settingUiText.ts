export const settingFieldLabels: Record<string, Record<string, string>> = {
  appearance: {
    if_show_tray: 'setting.basic.showTray',
    if_to_tray: 'setting.basic.minToTray',
    if_hide_close_button: 'setting.basic.hideClose',
  },
  start: {
    if_self_start: 'setting.func.autoStart',
    if_minimize_directly: 'setting.func.startMinimized',
  },
  function: {
    history_retention_time: 'setting.func.retention',
    if_allow_sleep: 'setting.func.preventSleep',
    if_silence: 'setting.func.silent',
    if_agree_bilibili: 'setting.func.biliPolicy',
    if_block_ad: 'setting.func.blockAds',
  },
  voice: {
    enabled: 'setting.func.voiceEnable',
    type: 'setting.func.voiceType',
  },
  display: {
    if_enable_virtual_display: 'setting.display.enable',
    virtual_display_mode: 'setting.display.mode',
  },
  notify: {
    send_task_result_time: 'setting.notify.resultTime',
    if_send_statistic: 'setting.notify.statistics',
    if_send_six_star: 'setting.notify.recruit',
    if_push_plyer: 'setting.notify.systemEnable',
    if_send_mail: 'setting.notify.mailEnable',
    if_koishi_support: 'setting.notify.koishiEnable',
    koishi_server_address: 'setting.notify.koishiWs',
    koishi_token: 'setting.notify.koishiToken',
    if_openclaw_qq: 'setting.notify.openclawQqEnable',
    openclaw_qq_app_id: 'setting.notify.qqAppId',
    openclaw_qq_client_secret: 'setting.notify.qqSecret',
    openclaw_qq_target_open_id: 'setting.notify.qqTarget',
    smtp_server_address: 'setting.notify.smtp',
    authorization_code: 'setting.notify.authCode',
    from_address: 'setting.notify.from',
    to_address: 'setting.notify.to',
    if_server_chan: 'setting.notify.serverChanEnable',
    server_chan_key: 'setting.notify.serverChanKey',
    test: 'setting.notify.sendTest',
  },
  updates: {
    if_auto_update: 'setting.others.updateBackend',
    source: 'setting.others.updateSource',
    channel: 'setting.others.updateChannel',
    proxy_address: 'setting.others.proxy',
    mirror_chyan_cdk: 'setting.others.cdk',
    github_token: 'setting.others.githubToken',
    pause_until: 'setting.others.pauseUpdates',
  },
}

export const settingFieldTips: Record<string, Record<string, string>> = {
  appearance: {
    if_show_tray: 'setting.basic.showTrayTip',
    if_to_tray: 'setting.basic.minToTrayTip',
    if_hide_close_button: 'setting.basic.hideCloseTip',
  },
  start: {
    if_self_start: 'setting.func.autoStartTip',
    if_minimize_directly: 'setting.func.startMinimizedTip',
  },
  function: {
    history_retention_time: 'setting.func.retentionTip',
    if_allow_sleep: 'setting.func.preventSleepTip',
    if_silence: 'setting.func.silentTip',
    if_agree_bilibili: 'setting.func.biliIntro',
    if_block_ad: 'setting.func.blockAdsIntro',
  },
  voice: {
    enabled: 'setting.func.voiceEnableTip',
    type: 'setting.func.voiceTypeTip',
  },
  display: {
    if_enable_virtual_display: 'setting.display.enableTip',
    virtual_display_mode: 'setting.display.modeTip',
  },
  notify: {
    send_task_result_time: 'setting.notify.resultTimeTip',
    if_send_statistic: 'setting.notify.statisticsTip',
    if_send_six_star: 'setting.notify.recruitTip',
    if_push_plyer: 'setting.notify.systemTip',
    if_send_mail: 'setting.notify.mailEnableTip',
    if_koishi_support: 'setting.notify.koishiTip',
    koishi_server_address: 'setting.notify.koishiWsTip',
    koishi_token: 'setting.notify.koishiTokenTip',
    if_openclaw_qq: 'setting.notify.openclawQqTip',
    openclaw_qq_app_id: 'setting.notify.qqAppIdTip',
    openclaw_qq_client_secret: 'setting.notify.qqSecretTip',
    openclaw_qq_target_open_id: 'setting.notify.qqTargetTip',
    smtp_server_address: 'setting.notify.smtpTip',
    authorization_code: 'setting.notify.authCodeTip',
    from_address: 'setting.notify.fromTip',
    to_address: 'setting.notify.toTip',
    if_server_chan: 'setting.notify.serverChanTip',
    server_chan_key: 'setting.notify.serverChanKeyTip',
  },
  updates: {
    if_auto_update: 'setting.others.updateBackendTip',
    source: 'setting.others.updateSourceTip',
    channel: 'setting.others.updateChannelTip',
    proxy_address: 'setting.others.proxyTip',
    mirror_chyan_cdk: 'setting.others.cdkHint',
    github_token: 'setting.others.githubTokenTip',
    pause_until: 'setting.others.pauseUpdatesTip',
  },
}

export const settingOptionLabels: Record<string, Record<string, Record<string, string>>> = {
  function: {
    history_retention_time: {
      '7': 'setting.retention.d7',
      '15': 'setting.retention.d15',
      '30': 'setting.retention.d30',
      '60': 'setting.retention.d60',
      '90': 'setting.retention.d90',
      '180': 'setting.retention.d180',
      '365': 'setting.retention.d365',
      '0': 'setting.retention.forever',
    },
  },
  voice: {
    type: { simple: 'setting.voice.simple', noisy: 'setting.voice.noisy' },
  },
  display: {
    virtual_display_mode: {
      '1920x1080@60': 'setting.display.refreshDefault',
      '1920x1080@30': 'setting.display.refreshLowPower',
    },
  },
  notify: {
    send_task_result_time: {
      不推送: 'setting.pushTime.never',
      仅失败时: 'setting.pushTime.failOnly',
      任何时刻: 'setting.pushTime.always',
    },
  },
  updates: {
    source: {
      GitHub: 'GitHub',
      MirrorChyan: 'setting.source.MirrorChyan',
      AutoSite: 'setting.source.AutoSite',
      CNB: 'setting.source.CNB',
    },
    channel: {
      stable: 'setting.channel.stable',
      beta: 'setting.channel.beta',
    },
  },
}
