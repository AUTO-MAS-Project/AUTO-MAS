interface ScriptSearchRecord {
  id?: unknown
  name?: unknown
  type?: unknown
  displayName?: unknown
  available?: unknown
  config?: unknown
  users?: readonly unknown[]
}

interface ScriptSearchKeyboardOptions {
  isActive: () => boolean
  isOpen: () => boolean
  open: () => void | Promise<void>
  close: () => void | Promise<void>
}

interface ScriptSearchFocusable {
  isConnected?: boolean
  focus: (options?: FocusOptions) => void
}

export interface ScriptSearchMatch {
  key: string
  kind: 'script' | 'user'
  scriptId: string
  userId?: string
}

export interface ScriptSearchResult<T extends ScriptSearchRecord> {
  scripts: T[]
  matches: ScriptSearchMatch[]
}

const SERVER_LABELS: Record<string, string> = {
  Official: '官服',
  Bilibili: 'B服',
  YoStarEN: '国际服',
  YoStarJP: '日服',
  YoStarKR: '韩服',
  txwy: '繁中服',
  'CN-Official': '官服',
  'CN-Bilibili': 'B服',
  'VN-Official': '越南服',
  'OVERSEA-America': '美服',
  'OVERSEA-Asia': '亚服',
  'OVERSEA-Europe': '欧服',
  'OVERSEA-TWHKMO': '港澳台服',
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const normalizeSearchText = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number'
    ? String(value).normalize('NFKC').toLocaleLowerCase()
    : ''

export const normalizeScriptSearchQuery = (query: string): string =>
  normalizeSearchText(query).trim()

const includesQuery = (value: unknown, query: string): boolean =>
  normalizeSearchText(value).includes(query)

const getValueByPath = (source: unknown, path: string): unknown => {
  if (!isRecord(source) || !path) return undefined
  return path.split('.').reduce<unknown>((current, key) => {
    if (!isRecord(current)) return undefined
    return current[key]
  }, source)
}

const parseTagTexts = (value: unknown): string[] => {
  if (!value || value === '-') return []

  let parsed: unknown = value
  if (typeof value === 'string') {
    try {
      parsed = JSON.parse(value) as unknown
    } catch {
      return [value]
    }
  }

  const values = Array.isArray(parsed) ? parsed : [parsed]
  return values.flatMap(item => {
    if (typeof item === 'string' || typeof item === 'number') return [String(item)]
    if (!isRecord(item)) return []
    const text = item.text ?? item.label ?? item.name
    return typeof text === 'string' || typeof text === 'number' ? [String(text)] : []
  })
}

const getSchemaTagTexts = (user: Record<string, unknown>): string[] => {
  const schema = user.schema
  if (!isRecord(schema)) return []

  const fields: Record<string, unknown>[] = Array.isArray(schema.groups)
    ? schema.groups.flatMap(group =>
        isRecord(group) && Array.isArray(group.fields) ? group.fields.filter(isRecord) : []
      )
    : Object.entries(schema).flatMap(([key, field]) =>
        isRecord(field) ? [{ ...field, key: field.key ?? key }] : []
      )

  const source = isRecord(user.config) ? user.config : user
  return fields.flatMap(field => {
    if (field.type !== 'tag') return []
    const path =
      typeof field.key === 'string' ? field.key : typeof field.name === 'string' ? field.name : ''
    return parseTagTexts(getValueByPath(source, path))
  })
}

const getScriptProjectLabel = (script: ScriptSearchRecord): string => {
  if (!isRecord(script.config) || !isRecord(script.config.Info)) return ''
  const projectLabel = script.config.Info.ProjectLabel
  return typeof projectLabel === 'string' ? projectLabel : ''
}

const getUserInfoRecords = (user: Record<string, unknown>) => {
  const records: Record<string, unknown>[] = []
  if (isRecord(user.Info)) records.push(user.Info)
  if (isRecord(user.config) && isRecord(user.config.Info)) records.push(user.config.Info)
  return records
}

const getUserVisibleSearchValues = (user: Record<string, unknown>): unknown[] => {
  const infoRecords = getUserInfoRecords(user)
  const values: unknown[] = [
    user.name,
    user.displayName,
    user.remark,
    user.remarks,
    user.note,
    user.notes,
  ]

  for (const info of infoRecords) {
    const server = typeof info.Server === 'string' ? info.Server : ''
    const resource = typeof info.Resource === 'string' ? info.Resource : ''
    values.push(
      info.Name,
      info.Id,
      info.Account,
      info.Notes,
      info.Note,
      info.Remark,
      info.Remarks,
      server,
      resource,
      SERVER_LABELS[server],
      SERVER_LABELS[resource],
      info.Status === true ? '启用' : info.Status === false ? '禁用' : '',
      ...parseTagTexts(info.Tag)
    )
  }

  values.push(...getSchemaTagTexts(user))
  return values
}

export const matchesScriptOwnSearch = (script: ScriptSearchRecord, rawQuery: string): boolean => {
  const query = normalizeScriptSearchQuery(rawQuery)
  if (!query) return true

  const type = typeof script.type === 'string' ? script.type : ''
  const candidates: unknown[] = [
    script.name,
    type,
    script.displayName,
    getScriptProjectLabel(script),
    script.available === false ? '未启用' : '',
    type === 'SRC' ? '配置SRC' : '',
    type === 'MaaEnd' ? '配置MaaEnd' : '',
  ]

  return candidates.some(value => includesQuery(value, query))
}

export const matchesUserSearch = (userValue: unknown, rawQuery: string): boolean => {
  const query = normalizeScriptSearchQuery(rawQuery)
  if (!query) return true
  if (!isRecord(userValue)) return false
  return getUserVisibleSearchValues(userValue).some(value => includesQuery(value, query))
}

export const matchesScriptSearch = (script: ScriptSearchRecord, rawQuery: string): boolean => {
  const query = normalizeScriptSearchQuery(rawQuery)
  if (!query || matchesScriptOwnSearch(script, query)) return true
  return (script.users ?? []).some(user => matchesUserSearch(user, query))
}

const asSearchId = (value: unknown, fallback: string): string => {
  const normalized = typeof value === 'string' || typeof value === 'number' ? String(value) : ''
  return normalized || fallback
}

export const getScriptSearchMatchKey = (scriptId: string): string => `script:${scriptId}`

export const getUserSearchMatchKey = (scriptId: string, userId: string): string =>
  `user:${scriptId}:${userId}`

export const buildScriptSearchResult = <T extends ScriptSearchRecord>(
  scripts: readonly T[],
  rawQuery: string
): ScriptSearchResult<T> => {
  const query = normalizeScriptSearchQuery(rawQuery)
  if (!query) return { scripts: [...scripts], matches: [] }

  const filteredScripts: T[] = []
  const matches: ScriptSearchMatch[] = []

  scripts.forEach((script, scriptIndex) => {
    const scriptId = asSearchId(script.id, `index-${scriptIndex}`)
    const scriptMatches = matchesScriptOwnSearch(script, query)
    const userMatches = (script.users ?? []).flatMap((user, userIndex) => {
      if (!matchesUserSearch(user, query)) return []
      const userId = asSearchId(isRecord(user) ? user.id : undefined, `index-${userIndex}`)
      return [
        {
          key: getUserSearchMatchKey(scriptId, userId),
          kind: 'user' as const,
          scriptId,
          userId,
        },
      ]
    })

    if (!scriptMatches && userMatches.length === 0) return
    filteredScripts.push(script)
    if (scriptMatches) {
      matches.push({
        key: getScriptSearchMatchKey(scriptId),
        kind: 'script',
        scriptId,
      })
    }
    matches.push(...userMatches)
  })

  return { scripts: filteredScripts, matches }
}

export const filterScriptsBySearch = <T extends ScriptSearchRecord>(
  scripts: readonly T[],
  query: string
): T[] => buildScriptSearchResult(scripts, query).scripts

export const reconcileActiveSearchMatchKey = (
  matches: readonly ScriptSearchMatch[],
  currentKey: string
): string => {
  if (currentKey && matches.some(match => match.key === currentKey)) return currentKey
  return matches[0]?.key ?? ''
}

export const getAdjacentSearchMatchKey = (
  matches: readonly ScriptSearchMatch[],
  currentKey: string,
  direction: 1 | -1
): string => {
  if (matches.length === 0) return ''
  const currentIndex = matches.findIndex(match => match.key === currentKey)
  if (currentIndex < 0) return direction === 1 ? matches[0].key : matches[matches.length - 1].key
  const nextIndex = (currentIndex + direction + matches.length) % matches.length
  return matches[nextIndex].key
}

export const isScriptSearchShortcut = (
  event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey'>
): boolean =>
  event.key.toLocaleLowerCase() === 'f' && (event.ctrlKey || event.metaKey) && !event.altKey

export const isEditableSearchTarget = (target: EventTarget | null): boolean => {
  if (!target || typeof target !== 'object') return false
  const candidate = target as {
    tagName?: unknown
    isContentEditable?: unknown
    closest?: (selector: string) => unknown
  }
  const tagName = typeof candidate.tagName === 'string' ? candidate.tagName.toUpperCase() : ''
  if (tagName === 'INPUT' || tagName === 'TEXTAREA') return true
  if (candidate.isContentEditable === true) return true
  return (
    typeof candidate.closest === 'function' &&
    Boolean(candidate.closest('[contenteditable]:not([contenteditable="false"])'))
  )
}

export const isKeyboardEventComposing = (
  event: Pick<KeyboardEvent, 'isComposing'> & { keyCode?: number }
): boolean => event.isComposing || event.keyCode === 229

export const getScriptSearchEnterDirection = (
  event: Pick<KeyboardEvent, 'key' | 'shiftKey' | 'isComposing'> & { keyCode?: number }
): 1 | -1 | null => {
  if (event.key !== 'Enter' || isKeyboardEventComposing(event)) return null
  return event.shiftKey ? -1 : 1
}

export const createScriptSearchFocusManager = () => {
  let restoreTarget: ScriptSearchFocusable | null = null

  const capture = (target: unknown) => {
    if (
      restoreTarget ||
      !target ||
      typeof target !== 'object' ||
      typeof (target as Partial<ScriptSearchFocusable>).focus !== 'function'
    ) {
      return
    }
    restoreTarget = target as ScriptSearchFocusable
  }

  const restore = () => {
    const target = restoreTarget
    restoreTarget = null
    if (!target || target.isConnected === false) return
    target.focus({ preventScroll: true })
  }

  const clear = () => {
    restoreTarget = null
  }

  return { capture, restore, clear }
}

export const createScriptSearchKeyboardController = (options: ScriptSearchKeyboardOptions) => {
  let activeTarget: EventTarget | null = null
  let activeListener: EventListener | null = null

  const handleKeydown = (event: KeyboardEvent) => {
    if (!options.isActive() || event.defaultPrevented || isKeyboardEventComposing(event)) return

    if (isScriptSearchShortcut(event)) {
      if (isEditableSearchTarget(event.target)) return
      event.preventDefault()
      void options.open()
      return
    }

    if (event.key === 'Escape' && options.isOpen()) {
      event.preventDefault()
      void options.close()
    }
  }

  const unbind = () => {
    if (activeTarget && activeListener) {
      activeTarget.removeEventListener('keydown', activeListener)
    }
    activeTarget = null
    activeListener = null
  }

  const bind = (target: EventTarget): (() => void) => {
    unbind()
    const listener: EventListener = event => handleKeydown(event as KeyboardEvent)
    activeTarget = target
    activeListener = listener
    target.addEventListener('keydown', listener)

    return () => {
      if (activeTarget !== target || activeListener !== listener) return
      unbind()
    }
  }

  return { bind, unbind, handleKeydown }
}
