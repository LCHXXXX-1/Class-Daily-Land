// ============================================================================
//  静态自检：没有浏览器也能查出来的那几类问题
//    1) 每个 JS 文件的语法
//    2) 用到的图标名是否都在 icons.js 里
//    3) patch() 回写的设置键是否都在宿主 mock 里（防止键名写错）
//    4) JS 里用到的每个 class 名是否在 CSS 里有定义（防止样式漏写）
//  跑法：node tests/static-check.mjs
// ============================================================================
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const ROOT = path.resolve(import.meta.dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");

const JS_FILES = ["host.js", "lib/icons.js", "lib/controls.js", "pages/app.js"];
const CSS_FILES = ["styles/tokens.css", "styles/app.css"];

let failures = 0;
const fail = (msg) => { console.log("  ✗ " + msg); failures++; };
const ok = (msg) => console.log("  ✓ " + msg);

// ---------------------------------------------------------------- 1) 语法
console.log("[1] JS 语法");
for (const file of JS_FILES) {
  try {
    execFileSync(process.execPath, ["--check", path.join(ROOT, file)], { stdio: ["ignore", "pipe", "pipe"] });
    ok(file);
  } catch (err) {
    fail(file + " :: " + String(err.stderr || err.message).split("\n")[0]);
  }
}

const iconsSrc = read("lib/icons.js");
const allJs = JS_FILES.map(read).join("\n");
const allCss = CSS_FILES.map(read).join("\n");

// ---------------------------------------------------------------- 2) 图标
console.log("[2] 图标名");
const defined = new Set([...iconsSrc.matchAll(/^\s{2}([a-z0-9]+):/gm)].map((m) => m[1]));
const used = new Set();
for (const m of allJs.matchAll(/iconEl\(\s*"([a-z0-9]+)"/g)) used.add(m[1]);
for (const m of allJs.matchAll(/icon:\s*"([a-z0-9]+)"/g)) used.add(m[1]);
for (const m of allJs.matchAll(/\{\s*success:\s*"([a-z0-9]+)",\s*warning:\s*"([a-z0-9]+)",\s*error:\s*"([a-z0-9]+)"/g)) {
  used.add(m[1]); used.add(m[2]); used.add(m[3]);
}
const missingIcons = [...used].filter((n) => !defined.has(n));
if (missingIcons.length) fail("icons.js 里缺：" + missingIcons.join(", "));
else ok(`用到的 ${used.size} 个图标都已定义（共定义 ${defined.size} 个）`);

// --------------------------------------------------- 3) 设置键与宿主 mock
console.log("[3] 设置键 ↔ 宿主 mock");
const mockBlock = read("host.js").match(/const MOCK_SETTINGS = \{([\s\S]*?)\n  \};/);
const mockKeys = new Set([...mockBlock[1].matchAll(/^\s{4}([a-z_0-9]+):/gm)].map((m) => m[1]));
const patched = new Set([...allJs.matchAll(/patch\(\s*"([a-z_0-9]+)"/g)].map((m) => m[1]));
const missingKeys = [...patched].filter((k) => !mockKeys.has(k));
if (missingKeys.length) fail("mock 里没有这些键：" + missingKeys.join(", "));
else ok(`页面回写的 ${patched.size} 个键在 mock 里都存在`);

// ---------------------------------------------------------------- 4) class
console.log("[4] class 名 ↔ CSS");
const cssClasses = new Set([...allCss.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
const usedClasses = new Set();
for (const m of allJs.matchAll(/class:\s*"([^"]+)"/g)) {
  m[1].split(/\s+/).filter(Boolean).forEach((c) => usedClasses.add(c));
}
for (const m of allJs.matchAll(/classList\.(?:add|toggle|remove)\("([^"]+)"/g)) usedClasses.add(m[1]);
const missingClasses = [...usedClasses].filter((c) => !cssClasses.has(c));
if (missingClasses.length) fail("CSS 里没有定义：" + missingClasses.join(", "));
else ok(`JS 用到的 ${usedClasses.size} 个 class 都有样式`);

console.log(failures === 0 ? "\n静态自检通过" : `\n静态自检发现 ${failures} 类问题`);
process.exit(failures === 0 ? 0 : 1);
