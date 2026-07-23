export interface OkScriptProjectProvider {
  resourceName: string
  displayName: string
  exeName: string
  configDir: string
  appJsonFile: string
  logFile: string
  pythonwPath: string
  gameProcessName: string
}

export const OK_SCRIPT_PROJECT_PROVIDERS: Record<string, OkScriptProjectProvider> = {
  'ok-ef': {
    resourceName: 'ok-ef',
    displayName: '明日方舟终末地',
    exeName: 'ok-ef.exe',
    configDir: 'data/apps/ok-ef/working/configs',
    appJsonFile: 'data/apps/ok-ef/app.json',
    logFile: 'data/apps/ok-ef/working/logs/ok-script.log',
    pythonwPath: 'data/apps/ok-ef/python/pythonw.exe',
    gameProcessName: 'Endfield.exe',
  },
  'ok-ww': {
    resourceName: 'ok-ww',
    displayName: '鸣潮',
    exeName: 'ok-ww.exe',
    configDir: 'data/apps/ok-ww/working/configs',
    appJsonFile: 'data/apps/ok-ww/app.json',
    logFile: 'data/apps/ok-ww/working/logs/ok-script.log',
    pythonwPath: 'data/apps/ok-ww/python/pythonw.exe',
    gameProcessName: 'Client-Win64-Shipping.exe',
  },
  'ok-nte': {
    resourceName: 'ok-nte',
    displayName: '异环',
    exeName: 'ok-nte.exe',
    configDir: 'data/apps/ok-nte/working/configs',
    appJsonFile: 'data/apps/ok-nte/app.json',
    logFile: 'data/apps/ok-nte/working/logs/ok-script.log',
    pythonwPath: 'data/apps/ok-nte/python/pythonw.exe',
    gameProcessName: 'HTGame.exe',
  },
}

export const getOkScriptProjectProvider = (resourceName?: string) =>
  resourceName ? OK_SCRIPT_PROJECT_PROVIDERS[resourceName] : undefined
