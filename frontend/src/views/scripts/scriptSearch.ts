import type { ScriptListItem, ScriptListUser } from '@/views/scripts/scriptListModel'
import { isMaaFWFamily, resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'

const normalizeSearchValue = (value: unknown) =>
  String(value ?? '')
    .trim()
    .toLowerCase()

const includesKeyword = (values: unknown[], keyword: string) =>
  values.some(value => normalizeSearchValue(value).includes(keyword))

const matchesUser = (user: ScriptListUser, keyword: string) =>
  includesKeyword([user.name, user.id, user.Info.Name, user.Info.Id], keyword)

// MFW 家族卡片上的类型标签显示的是项目名（Info.ProjectLabel），没有时是类型标签（MFW / M9A …）：
// 看得见的名字都要能搜到
const scriptDisplayValues = (script: ScriptListItem): unknown[] =>
  isMaaFWFamily(script.type)
    ? [script.projectLabel, resolveMaaFWFlavor(script.type).typeTagLabel]
    : []

export const filterScriptsByKeyword = (
  scripts: ScriptListItem[],
  rawKeyword: string
): ScriptListItem[] => {
  const keyword = normalizeSearchValue(rawKeyword)
  if (!keyword) return scripts

  return scripts.flatMap(script => {
    if (
      includesKeyword(
        [script.name, script.id, script.type, ...scriptDisplayValues(script)],
        keyword
      )
    ) {
      return [script]
    }

    const matchingUsers = script.users.filter(user => matchesUser(user, keyword))
    return matchingUsers.length ? [{ ...script, users: matchingUsers }] : []
  })
}
