// AUTO-MAS frontend 工具：`yarn openapi` 生成后把 src/api 收拾干净。
//
// 背景：openapi-typescript-codegen 在 Windows 上按 CRLF 写出，而仓库 .gitattributes
// 强制 *.ts eol=lf；且 .oxfmtrc.json 的 ignorePatterns 忽略了 src/api，yarn format
// 也管不到。结果生成一次，git status 就会冒出一大批「只有换行符不同」的已修改文件
// （git diff 内容却为空），只能手工清。
//
// 这里做两件事：
//   1. 把 src/api 下文本文件的换行符统一成 LF（只改换行符，不动内容）；
//   2. 刷新这些文件的 git 索引缓存。CRLF 写盘会让 git 把它们标记为「待 renormalize」，
//      仅把工作区改回 LF 还不够——`git update-index --refresh` 无效，必须
//      `git add --renormalize` 才清得掉假阳性；紧接着 reset 撤掉暂存，
//      保持「生成物已落盘、但没替你 staged」的原有习惯。
//
// 用法：node scripts/postprocess-openapi.mjs（由 package.json 的 openapi 脚本串联）

import { execFileSync } from 'node:child_process'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const apiDir = join(frontendDir, 'src', 'api')

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(full)
    else if (entry.isFile()) yield full
  }
}

let normalized = 0
for await (const file of walk(apiDir)) {
  const content = await readFile(file, 'utf8')
  if (!content.includes('\r\n')) continue
  await writeFile(file, content.replaceAll('\r\n', '\n'), 'utf8')
  normalized += 1
}
console.log(`postprocess-openapi: ${normalized} 个文件换行符已统一为 LF`)

try {
  // 只碰生成目录：先 renormalize 刷新索引缓存，再撤销暂存
  execFileSync('git', ['add', '--renormalize', '--', 'src/api'], {
    cwd: frontendDir,
    stdio: 'pipe',
  })
  execFileSync('git', ['reset', '-q', '--', 'src/api'], {
    cwd: frontendDir,
    stdio: 'pipe',
  })
  console.log('postprocess-openapi: git 索引缓存已刷新')
} catch (error) {
  // 非源码环境（无 git 或非仓库）不应让生成流程失败
  console.warn(`postprocess-openapi: 跳过 git 索引刷新：${error.message}`)
}
