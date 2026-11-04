"""逐项测试清理的清单与复核工具，不加入 CI。

用法：python scripts/audit_checks.py inventory <ref> <输出.json>
      python scripts/audit_checks.py verify <审查.json>
清单记录基线中的每个测试定义；参数化展开不重复计数。
"""

import ast
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 使用项目已有 TypeScript 解析器，只发现测试，不按名称自动决定去留。
JS_INVENTORY = r"""
const ts = require('./frontend/node_modules/typescript');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  const output = [];
  for (const [path, text] of JSON.parse(input)) {
    const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true);
    const tests = [];
    function visit(node) {
      if (ts.isCallExpression(node)) {
        const expression = node.expression.getText(source);
        if (/^(it|test)(\.(skip|only|todo|each|skipIf|runIf)(\([^]*\))?)*$/.test(expression)
            && node.arguments.length > 0
            && (ts.isStringLiteralLike(node.arguments[0]) || ts.isTemplateExpression(node.arguments[0]))) {
          const name = node.arguments[0].getText(source);
          const start = node.getStart(source);
          tests.push({name, line: source.getLineAndCharacterOfPosition(start).line + 1,
            source: text.slice(start, node.end)});
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(source);
    output.push([path, tests]);
  }
  process.stdout.write(JSON.stringify(output));
});
"""


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def inventory(ref):
    paths = git("ls-tree", "-r", "--name-only", ref).decode().splitlines()
    selected = [
        path
        for path in paths
        if (path.endswith(".py") and Path(path).name.startswith("test_"))
        or path.endswith((".test.ts", ".spec.ts", ".pw.ts", ".check.mjs"))
    ]
    batch = subprocess.check_output(
        ["git", "cat-file", "--batch"],
        input="".join(f"{ref}:{path}\n" for path in selected).encode(),
        cwd=ROOT,
    )
    sources = {}
    offset = 0
    for path in selected:
        end = batch.index(b"\n", offset)
        size = int(batch[offset:end].split()[2])
        sources[path] = batch[end + 1 : end + 1 + size].decode("utf-8-sig")
        offset = end + size + 2
    return discover(sources)


def discover(sources):
    tests = []
    javascript = []
    for path, source in sources.items():
        if not path.endswith(".py"):
            javascript.append((path, source))
            continue
        lines = source.splitlines()

        def visit(body, prefix=""):
            for node in body:
                if isinstance(node, ast.ClassDef):
                    visit(node.body, f"{prefix}{node.name}.")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test"):
                        start = min(
                            [node.lineno, *[d.lineno for d in node.decorator_list]]
                        )
                        tests.append(
                            {
                                "path": path,
                                "name": prefix + node.name,
                                "line": start,
                                "source": "\n".join(lines[start - 1 : node.end_lineno]),
                            }
                        )

        visit(ast.parse(source).body)
    if javascript:
        result = subprocess.check_output(
            ["node", "-e", JS_INVENTORY],
            input=json.dumps(javascript).encode(),
            cwd=ROOT,
        )
        for path, entries in json.loads(result):
            tests.extend({"path": path, **entry} for entry in entries)
    counts = Counter()
    for test in tests:
        key = f"{test['path']}::{test['name']}"
        counts[key] += 1
        test["id"] = key + (f"#{counts[key]}" if counts[key] > 1 else "")
        test["sha256"] = hashlib.sha256(test["source"].encode()).hexdigest()
    return tests


def verify(path):
    audit = json.loads(path.read_text(encoding="utf-8"))
    original = inventory(audit["base"])
    decisions = {entry["id"]: entry for entry in audit["tests"]}
    errors = []
    if len(decisions) != len(audit["tests"]):
        errors.append("重复审查记录")
    if set(decisions) != {test["id"] for test in original}:
        errors.append("审查记录未完整覆盖基线")
    sources = {
        path: (ROOT / path).read_text(encoding="utf-8-sig")
        for path in {test["path"] for test in original}
        if (ROOT / path).exists()
    }
    current = Counter((test["path"], test["sha256"]) for test in discover(sources))
    expected = Counter()
    for test in original:
        entry = decisions.get(test["id"], {})
        if entry.get("decision") not in ("keep", "delete") or not entry.get("reason"):
            errors.append(f"未审查: {test['id']}")
        if entry.get("decision") == "keep":
            expected[test["path"], test["sha256"]] += 1
    if current != expected:
        errors.append(
            f"保留/删除结果与清单不符: {current - expected=}, {expected - current=}"
        )
    counts = Counter(entry.get("decision", "pending") for entry in audit["tests"])
    print(
        json.dumps(
            {"base": audit["base"], "tests": dict(counts), "errors": errors},
            ensure_ascii=False,
            indent=2,
        )
    )
    return bool(errors)


if __name__ == "__main__":
    if sys.argv[1] == "inventory":
        tests = inventory(sys.argv[2])
        Path(sys.argv[3]).write_text(
            json.dumps(tests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{len(tests)} test definitions in {len({test['path'] for test in tests})} files"
        )
    elif sys.argv[1] == "verify":
        sys.exit(verify(Path(sys.argv[2])))
    else:
        raise SystemExit("inventory <ref> <output.json> | verify <audit.json>")
