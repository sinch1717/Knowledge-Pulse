// Exports the interfaces in src/lib/types.ts as JSON, for the backend's
// frontend-contract test (backend/tests/suites/integration/test_contract.py).
//
//   node scripts/export-api-types.mjs > ../backend/tests/suites/.generated/frontend_types.json
//
// Uses the TypeScript compiler already in devDependencies; nothing to install.
// For every interface: each property, whether it is optional, and, when its
// type is another interface or an inline object (arrays included), what that is.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import ts from "typescript";

const here = dirname(fileURLToPath(import.meta.url));
const file = join(here, "..", "src", "lib", "types.ts");
const source = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true);

function describeType(node) {
  if (!node) return { text: "unknown" };
  if (ts.isArrayTypeNode(node)) return { array: true, ...describeType(node.elementType) };
  if (ts.isTypeReferenceNode(node)) return { text: node.getText(source), ref: node.typeName.getText(source) };
  if (ts.isTypeLiteralNode(node)) return { text: "object", props: members(node.members) };
  if (ts.isUnionTypeNode(node)) {
    const parts = node.types.filter((t) => t.kind !== ts.SyntaxKind.NullKeyword && !(ts.isLiteralTypeNode(t) && t.literal.kind === ts.SyntaxKind.NullKeyword));
    const nullable = parts.length !== node.types.length;
    const inner = parts.length === 1 ? describeType(parts[0]) : { text: node.getText(source) };
    return { ...inner, nullable };
  }
  return { text: node.getText(source) };
}

function members(list) {
  const out = {};
  for (const m of list) {
    if (!ts.isPropertySignature(m)) continue;
    out[m.name.getText(source)] = { optional: Boolean(m.questionToken), ...describeType(m.type) };
  }
  return out;
}

const interfaces = {};
const heritage = {};
ts.forEachChild(source, (node) => {
  if (ts.isInterfaceDeclaration(node)) {
    interfaces[node.name.text] = members(node.members);
    heritage[node.name.text] = (node.heritageClauses ?? []).flatMap((h) => h.types.map((t) => t.expression.getText(source)));
  }
});

// Fold inherited properties in (InsightDetail extends Insight).
function resolve(name, seen = new Set()) {
  if (seen.has(name)) return {};
  seen.add(name);
  return (heritage[name] ?? []).reduce((acc, parent) => ({ ...resolve(parent, seen), ...acc }), { ...interfaces[name] });
}

const result = Object.fromEntries(Object.keys(interfaces).map((n) => [n, resolve(n)]));
process.stdout.write(JSON.stringify(result, null, 2) + "\n");
