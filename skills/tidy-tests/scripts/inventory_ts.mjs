#!/usr/bin/env node
// Inventory vitest/jest test files with the TypeScript compiler API. Called by inventory.py:
//   node inventory_ts.mjs ROOT FILE...   → JSON {tests, files} on stdout
// `typescript` is resolved from $INVENTORY_TYPESCRIPT (a path to an installed typescript package)
// or the test files' own node_modules. TypeScript 7 (native) has no JS compiler API; such a project
// needs INVENTORY_TYPESCRIPT pointing at any 5.x/6.x install.
import { createRequire } from "node:module";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const [root, ...files] = process.argv.slice(2);

function loadTypescript() {
  const tried = [];
  const attempts = [];
  if (process.env.INVENTORY_TYPESCRIPT) {
    attempts.push(() => createRequire(import.meta.url)(path.resolve(process.env.INVENTORY_TYPESCRIPT)));
  }
  for (const from of [...files, path.join(process.cwd(), "x.js")]) {
    attempts.push(() => createRequire(path.resolve(from))("typescript"));
  }
  for (const attempt of attempts) {
    try {
      const ts = attempt();
      if (typeof ts?.createSourceFile === "function") return ts;
      tried.push(`typescript ${ts?.version ?? "?"} (no JS compiler API)`);
    } catch {}
  }
  console.error(`no usable typescript (${tried.join(", ") || "none found"}).\n` +
    "Install one into the scratch dir — do not borrow another project's — and point at it:\n" +
    '  npm install --prefix "$S/ts" typescript@5\n' +
    '  INVENTORY_TYPESCRIPT="$S/ts/node_modules/typescript" python3 inventory.py ...\n' +
    "(If the sandbox has no network, ask the user for approval, or skip the TS inventory and read the files.)");
  process.exit(2);
}
const ts = loadTypescript();

const TEST_FNS = new Set(["it", "test"]);
const SUITE_FNS = new Set(["describe", "suite", "context"]);
const MOCK_MATCHER = /^(toHaveBeenCalled\w*|toBeCalled\w*|lastCalledWith|nthCalledWith|toHaveReturned\w*|toHaveLastReturnedWith|toHaveNthReturnedWith|toHaveBeenLastCalledWith|toHaveBeenNthCalledWith)$/;
const SNAPSHOT_MATCHER = /^(toMatchSnapshot|toMatchInlineSnapshot|toMatchFileSnapshot|toThrowErrorMatchingSnapshot|toThrowErrorMatchingInlineSnapshot)$/;
const PRESENCE_MATCHER = new Set(["toBeTruthy", "toBeDefined", "toBeInTheDocument"]);
const HELPER_ASSERT = /^_?(assert|check|expect|verify|ensure|should)\w+/i;
const QUERY = /^(getBy|getAllBy|findBy|findAllBy)\w+$/;
const MOCK_FACTORY = /^(fn|spyOn|mocked)$/;
const MOCK_SETUP = /^mock(ResolvedValue|RejectedValue|ReturnValue|Implementation)(Once)?$/;
const FIRST_PARTY = /^(\.|@\/|~\/|src\/)/;

const lineOf = (sf, node) => sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
const endLineOf = (sf, node) => sf.getLineAndCharacterOfPosition(node.getEnd()).line + 1;

function tokenHash(sf, text) {
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, true, sf.languageVariant, text);
  const parts = [];
  for (let k = scanner.scan(); k !== ts.SyntaxKind.EndOfFileToken; k = scanner.scan()) parts.push(scanner.getTokenText());
  return crypto.createHash("sha1").update(parts.join("\u0001")).digest("hex");
}

// it / it.skip / it.each(table) / it.skipIf(c) / test.concurrent.each`...` → {base, mods, each}
function describeCallee(expr) {
  const mods = [];
  let each = false;
  let node = expr;
  for (;;) {
    if (ts.isCallExpression(node)) node = node.expression;
    else if (ts.isTaggedTemplateExpression(node)) node = node.tag;
    else if (ts.isPropertyAccessExpression(node)) {
      const name = node.name.text;
      if (name === "each" || name === "for") each = true;
      mods.unshift(name);
      node = node.expression;
    } else if (ts.isIdentifier(node)) return { base: node.text, mods, each };
    else return null;
  }
}

function titleOf(sf, arg) {
  if (!arg) return "";
  if (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) return arg.text;
  if (ts.isTemplateExpression(arg)) return arg.getText(sf).slice(1, -1);
  return arg.getText(sf);
}

// expect(x).not.toBe(1) → walk up from the expect() call to the matcher name
function matcherOf(expectCall) {
  const chain = [];
  let node = expectCall;
  while (ts.isPropertyAccessExpression(node.parent) && node.parent.expression === node) {
    chain.push(node.parent.name.text);
    node = node.parent;
  }
  const call = ts.isCallExpression(node.parent) && node.parent.expression === node ? node.parent : null;
  return { chain, matcher: chain.at(-1) ?? "", args: call ? call.arguments : [] };
}

const unwrap = (n) => (n && (ts.isAwaitExpression(n) || ts.isParenthesizedExpression(n)) ? unwrap(n.expression) : n);

function calleeName(call) {
  const c = call.expression;
  return ts.isIdentifier(c) ? c.text : ts.isPropertyAccessExpression(c) ? c.name.text : "";
}

// The identifier a mock assertion is about: expect(fn) / expect(vi.mocked(fn)) / expect(fn.mock.calls…)
function mockSubject(subject) {
  let n = unwrap(subject);
  if (n && ts.isCallExpression(n) && calleeName(n) === "mocked" && n.arguments[0]) n = n.arguments[0];
  while (n && (ts.isPropertyAccessExpression(n) || ts.isElementAccessExpression(n))) n = n.expression;
  return n && ts.isIdentifier(n) ? n.text : "";
}

function classifyExpect(sf, expectCall, mockedImports) {
  const { chain, matcher, args } = matcherOf(expectCall);
  const negated = chain.includes("not");
  const subjectNode = unwrap(expectCall.arguments[0]);
  const subject = subjectNode?.getText(sf) ?? "";
  const out = { kind: "strong", broadThrow: false, mockTarget: "", negativeMock: "", negativeString: "", status: false };
  const lit = (n) => (n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) ? n.text : "");
  if (negated && ["toContain", "toMatch", "toHaveTextContent"].includes(matcher)) out.negativeString = lit(args[0]);
  // expect(screen.queryByText("x")).toBeNull() / .not.toBeInTheDocument(): "x" must not render
  if (subjectNode && ts.isCallExpression(subjectNode) && /^query(All)?By(Text|LabelText|PlaceholderText|Title|AltText|DisplayValue)$/.test(calleeName(subjectNode)) &&
      (matcher === "toBeNull" && !negated || matcher === "toBeInTheDocument" && negated)) out.negativeString = lit(subjectNode.arguments[0]);
  if (/\.status(Code)?$/.test(subject) || (matcher === "toHaveProperty" && lit(args[0]) === "status")) out.status = true;
  if (MOCK_MATCHER.test(matcher) || /\.mock\.(calls|results|lastCall|instances)/.test(subject)) {
    out.kind = "mock";
    const name = mockSubject(expectCall.arguments[0]);
    out.mockTarget = mockedImports.has(name) ? "module" : "callback";
    if (negated && name) out.negativeMock = name;
    return out;
  }
  if (SNAPSHOT_MATCHER.test(matcher)) return { ...out, kind: "snapshot" };
  // expect(screen.getByText("x")).toBeTruthy(): the query throws when missing, so this is a real presence check
  const isQuery = subjectNode && ts.isCallExpression(subjectNode) && QUERY.test(calleeName(subjectNode));
  if (isQuery && (PRESENCE_MATCHER.has(matcher) || (negated && matcher === "toBeNull"))) return out;
  if (["toBeDefined", "toBeTruthy", "toBeInstanceOf", "toBeTypeOf"].includes(matcher) && !negated) return { ...out, kind: "weak" };
  if (["toBeNull", "toBeUndefined"].includes(matcher) && negated) return { ...out, kind: "weak" };
  if (matcher === "toThrow" || matcher === "toThrowError") {
    if (negated) return { ...out, kind: "weak" };
    if (args.length === 0) return { ...out, kind: "weak", broadThrow: true };
  }
  if ((matcher === "toBeGreaterThan" && args[0]?.getText(sf) === "0") ||
      (matcher === "toBeGreaterThanOrEqual" && ["0", "1"].includes(args[0]?.getText(sf)))) return { ...out, kind: "weak" };
  return out;
}

function scanTestBody(sf, fn, mockedImports) {
  const c = { asserts: 0, strong: 0, weak: 0, mock: 0, snapshot: 0, helper: 0, implicit: 0, mocks: 0, waits: 0,
              moduleMock: 0, callbackMock: 0 };
  const flags = new Set();
  const negativeMocks = new Set();
  const negativeStrings = [];
  let statusAsserts = 0;
  const count = (kind, node) => {
    c.asserts += 1;
    c[kind] += 1;
    let p = node.parent, inLoop = false, inCond = false;
    while (p && p !== fn) {
      if (ts.isForStatement(p) || ts.isForOfStatement(p) || ts.isForInStatement(p) || ts.isWhileStatement(p)) inLoop = true;
      if (ts.isCallExpression(p) && ts.isPropertyAccessExpression(p.expression) &&
          ["forEach", "map", "every", "some"].includes(p.expression.name.text)) inLoop = true;
      if (ts.isIfStatement(p) || ts.isConditionalExpression(p) ||
          (ts.isBinaryExpression(p) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken].includes(p.operatorToken.kind))) inCond = true;
      if (ts.isTryStatement(p) && p.catchClause) {
        const handler = p.catchClause.block.getText(sf);
        if (!/\bthrow\b|expect\(|fail\(/.test(handler)) flags.add("swallowed-assert");
      }
      p = p.parent;
    }
    if (inCond && !inLoop) flags.add("conditional-assert");
  };
  const visit = (node) => {
    if (ts.isCallExpression(node)) {
      const callee = node.expression;
      const name = calleeName(node);
      const owner = ts.isPropertyAccessExpression(callee) ? callee.expression.getText(sf) : "";
      if (ts.isIdentifier(callee) && callee.text === "expect") {
        const r = classifyExpect(sf, node, mockedImports);
        count(r.kind, node);
        if (r.broadThrow) flags.add("broad-throws");
        if (r.mockTarget === "module") c.moduleMock += 1;
        if (r.mockTarget === "callback") c.callbackMock += 1;
        if (r.negativeMock) negativeMocks.add(r.negativeMock);
        if (r.negativeString) negativeStrings.push(r.negativeString);
        if (r.status) statusAsserts += 1;
      } else if (owner === "expect" && ["soft", "poll", "element"].includes(name)) {
        count("strong", node);
      } else if (owner === "expect" && ["assertions", "hasAssertions"].includes(name)) {
        // meta-assertion: counts calls, detects nothing about values
      } else if ((ts.isIdentifier(callee) && callee.text === "assert") || owner === "assert") {
        count("strong", node);
      } else if (ts.isIdentifier(callee) && HELPER_ASSERT.test(callee.text)) {
        count("helper", node);
      } else if (QUERY.test(name)) {
        c.implicit += 1;
      } else if ((owner === "vi" || owner === "jest") && MOCK_FACTORY.test(name)) {
        c.mocks += 1;
      } else if (MOCK_SETUP.test(name)) {
        c.mocks += 1;
      } else if (name === "waitFor" || name === "waitForElementToBeRemoved") {
        c.waits += 1;
      } else if (name === "setTimeout" && node.arguments[1] && node.arguments[1].getText(sf) !== "0") {
        flags.add("sleeps");
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(fn.body);
  if (statusAsserts && statusAsserts === c.asserts) flags.add("status-only");
  return { c, flags, negativeMocks: [...negativeMocks], negativeStrings };
}

const allTests = [];
const fileMeta = [];
for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  const kind = file.endsWith(".tsx") ? ts.ScriptKind.TSX : file.endsWith(".jsx") ? ts.ScriptKind.JSX
    : /\.[cm]?js$/.test(file) ? ts.ScriptKind.JS : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  const rel = path.relative(root, file);

  // imports: module specifiers, local names (value imports only), and which come from vi.mock'ed modules
  const imports = [];
  const moduleMocks = [];
  const importedLocals = new Map(); // local name → {module, imported}
  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st) && ts.isStringLiteral(st.moduleSpecifier)) {
      const spec = st.moduleSpecifier.text;
      imports.push(spec);
      const clause = st.importClause;
      if (!clause || clause.isTypeOnly) continue;
      if (clause.name) importedLocals.set(clause.name.text, { module: spec, imported: "default" });
      const nb = clause.namedBindings;
      if (nb && ts.isNamedImports(nb)) {
        for (const el of nb.elements) {
          if (!el.isTypeOnly) importedLocals.set(el.name.text, { module: spec, imported: (el.propertyName ?? el.name).text });
        }
      } else if (nb && ts.isNamespaceImport(nb)) {
        importedLocals.set(nb.name.text, { module: spec, imported: "*" });
      }
    }
  }
  const findMocks = (node) => {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression) &&
        ["vi", "jest"].includes(node.expression.expression.getText(sf)) &&
        ["mock", "doMock"].includes(node.expression.name.text) && node.arguments[0] && ts.isStringLiteralLike(node.arguments[0])) {
      moduleMocks.push(node.arguments[0].text);
    }
    ts.forEachChild(node, findMocks);
  };
  findMocks(sf);
  const mockedImports = new Set([...importedLocals].filter(([, v]) => moduleMocks.includes(v.module)).map(([k]) => k));

  // unused imports: an imported name never referenced again — often the trace of a deleted test
  const refs = new Map();
  const countRefs = (node) => {
    if (ts.isImportDeclaration(node)) return;
    if (ts.isIdentifier(node)) refs.set(node.text, (refs.get(node.text) ?? 0) + 1);
    ts.forEachChild(node, countRefs);
  };
  countRefs(sf);
  const unusedImports = [...importedLocals].filter(([local]) => !refs.get(local)).map(([local, v]) => `${v.module}:${local}`);
  const symbols = [...new Set([...importedLocals.values()]
    .filter((v) => FIRST_PARTY.test(v.module) && !["default", "*"].includes(v.imported)).map((v) => v.imported))].sort();

  const tests = [];
  const suiteStack = [];
  const visit = (node) => {
    if (ts.isCallExpression(node)) {
      const info = describeCallee(node.expression);
      const fn = [...node.arguments].reverse().find((a) => ts.isArrowFunction(a) || ts.isFunctionExpression(a));
      if (info && SUITE_FNS.has(info.base)) {
        suiteStack.push(titleOf(sf, node.arguments[0]));
        ts.forEachChild(node, visit);
        suiteStack.pop();
        return;
      }
      if (info && TEST_FNS.has(info.base)) {
        const name = titleOf(sf, node.arguments[0]);
        const markers = info.mods.filter((m) => m !== "each" && m !== "for");
        if (info.each) markers.push("each");
        const flags = new Set();
        let c = { asserts: 0, strong: 0, weak: 0, mock: 0, snapshot: 0, helper: 0, implicit: 0, mocks: 0, waits: 0, moduleMock: 0, callbackMock: 0 };
        let hash = "", steps = [], negativeMocks = [], negativeStrings = [];
        if (fn && fn.body) {
          const scan = scanTestBody(sf, fn, mockedImports);
          c = scan.c;
          negativeMocks = scan.negativeMocks;
          negativeStrings = scan.negativeStrings;
          scan.flags.forEach((f) => flags.add(f));
          if (ts.isBlock(fn.body)) {
            hash = tokenHash(sf, fn.body.getText(sf)).slice(0, 10);
            steps = fn.body.statements.map((st) => tokenHash(sf, st.getText(sf)).slice(0, 8));
          }
        }
        if (markers.some((m) => ["skip", "todo"].includes(m)) || !fn) flags.add("skipped");
        if (c.asserts === 0) flags.add(c.implicit ? "implicit-only" : "no-assert");
        else if (c.mock === c.asserts) flags.add(c.moduleMock ? "mock-only" : "callback-only");
        else if (c.weak === c.asserts) flags.add("weak-only");
        if (c.snapshot && c.snapshot === c.asserts) flags.add("snapshot-only");
        if (c.mocks >= 3) flags.add("mock-heavy");
        const suite = suiteStack.join(" > ");
        const line = lineOf(sf, node), end = endLineOf(sf, node);
        tests.push({
          kind: "ts", file: rel, suite, suite_path: [...suiteStack], name,
          id: `${rel}::${suite ? suite + " > " : ""}${name}`,
          line, end_line: end, loc: end - line + 1, rows: info.each ? "?" : 1, markers, each: info.each,
          asserts: c.asserts, strong: c.strong, weak: c.weak, mock_asserts: c.mock, helper_asserts: c.helper,
          snapshots: c.snapshot, implicit: c.implicit, mocks: c.mocks, waits: c.waits,
          fixtures: [], flags: [...flags].sort(), hash, steps, negative_mock_subjects: negativeMocks,
          negative_strings: negativeStrings,
        });
        return;
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  const lines = text.split("\n").length;
  const testLines = tests.reduce((n, t) => n + t.loc, 0);
  allTests.push(...tests);
  fileMeta.push({ file: rel, kind: "ts", lines, tests: tests.length, support_lines: lines - testLines, imports,
                  module_mocks: moduleMocks, unused_imports: unusedImports, symbols });
}
process.stdout.write(JSON.stringify({ tests: allTests, files: fileMeta }));
