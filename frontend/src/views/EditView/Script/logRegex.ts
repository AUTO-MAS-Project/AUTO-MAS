/**
 * 日志正则校验：成功/失败标志的正则模式与日志处理钩子规则共用
 *
 * 后端按 Python 正则编译，浏览器只能用 JavaScript 正则近似校验。为避免把合法的
 * Python 正则误报为错误，先把 Python 独有的具名分组语法归一为 JavaScript 写法，
 * 再交给 RegExp 编译；两边都非法的语法错误才会被拦下。校验只用于给出编辑期提示，
 * 后端仍是唯一判据：非法正则在运行时只是永不命中，不会中断任务执行。
 */

const PYTHON_NAMED_GROUP_RE = /\(\?P</g
const PYTHON_NAMED_BACKREF_RE = /\(\?P=(\w+)\)/g

/** 把 Python 具名分组语法归一为 JavaScript 等价写法，供 RegExp 试编译 */
export const toJsRegexSource = (pattern: string): string =>
  pattern.replace(PYTHON_NAMED_GROUP_RE, '(?<').replace(PYTHON_NAMED_BACKREF_RE, '\\k<$1>')

/**
 * 校验正则语法
 *
 * @returns 语法错误信息；为空串或语法正确时返回 null
 */
export const validateRegexPattern = (pattern: string): string | null => {
  const source = (pattern || '').trim()
  if (!source) return null
  try {
    new RegExp(toJsRegexSource(source))
    return null
  } catch (error) {
    return error instanceof Error ? error.message : String(error)
  }
}
