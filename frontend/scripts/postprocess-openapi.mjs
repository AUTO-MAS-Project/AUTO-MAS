// AUTO-MAS frontend 工具：`yarn openapi` 生成后把 src/api 收拾干净。
//
// 背景：openapi-typescript-codegen 在 Windows 上按 CRLF 写出，而仓库 .gitattributes
// 强制 *.ts eol=lf；且 .oxfmtrc.json 的 ignorePatterns 忽略了 src/api，yarn format
// 也管不到。结果生成一次，git status 就会冒出一大批「只有换行符不同」的已修改文件
// （git diff 内容却为空）。
//
// 这里只做一件事：把 src/api 下文本文件的换行符统一成 LF（只改换行符，不动内容）。
// 不做任何 git 操作：换行符归一后 git status 的比较即恢复一致，索引会在下次
// git status/git add 时自行刷新；这里若动索引（如 add/reset）反而会丢掉用户
// 在 src/api 里已暂存的内容。无 git 的环境因此也不受影响。
//
// 用法：node scripts/postprocess-openapi.mjs（由 package.json 的 openapi 脚本串联）

import { readdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const apiDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'api')

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
