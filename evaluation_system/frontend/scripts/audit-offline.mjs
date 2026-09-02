import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { dirname } from "node:path";

const root = resolve(import.meta.dirname, "..");
const roots = ["src", "public", "index.html", "vite.config.ts", "dist"];
const textExtensions = new Set([".html", ".css", ".js", ".mjs", ".ts", ".tsx", ".json", ".svg", ".txt"]);
const tokens = ["http://", "https://", "cdnjs", "jsdelivr", "unpkg", "googleapis", "gstatic", "fonts.googleapis", "fonts.gstatic"];
const classifiedHarmless = [
  /^http:\/\/127\.0\.0\.1(?::\d+)?(?:\/|$)/,
  /^http:\/\/www\.w3\.org\/(?:1999\/xhtml|2000\/svg)$/,
  /^http:\/\/www\.w3\.org\/(?:1998\/Math\/MathML|1999\/xlink|XML\/1998\/namespace)$/,
  /^https:\/\/react\.dev\/errors\//,
];

function filesAt(path) {
  if (!existsSync(path)) return [];
  if (!statSync(path).isDirectory()) return [path];
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => filesAt(join(path, entry.name)));
}

function externalLiterals(text) {
  const urls = text.match(/https?:\/\/[^\s"'`<>\\)]+/g) || [];
  const tokenHits = tokens.flatMap((token) => text.toLowerCase().includes(token) ? [token] : []);
  return { urls, tokenHits };
}

const violations = [];
const classified = [];
for (const sourceRoot of roots) {
  for (const file of filesAt(join(root, sourceRoot))) {
    if (!textExtensions.has(extname(file))) continue;
    const text = readFileSync(file, "utf8");
    const relativeFile = relative(root, file);
    const { urls, tokenHits } = externalLiterals(text);
    for (const url of urls) {
      const licenseDocumentation = relativeFile === "public/fonts/Vazirmatn-OFL.txt" || relativeFile === "dist/fonts/Vazirmatn-OFL.txt";
      if (licenseDocumentation || classifiedHarmless.some((rule) => rule.test(url))) classified.push({ file: relativeFile, value: url });
      else violations.push({ file: relativeFile, value: url });
    }
    for (const token of tokenHits) {
      if ((token === "http://" || token === "https://") && urls.length) continue;
      violations.push({ file: relativeFile, value: token });
    }
    if (sourceRoot === "dist" && extname(file) === ".css") {
      const assetRefs = [...text.matchAll(/url\(["']?([^"')]+)["']?\)/g)].map((match) => match[1]);
      for (const ref of assetRefs) {
        if (/^(?:data:|#)/.test(ref)) continue;
        if (/^(?:https?:)?\/\//.test(ref)) violations.push({ file: relative(root, file), value: `external CSS asset ${ref}` });
        else {
          const target = ref.startsWith("/") ? resolve(root, "dist", ref.slice(1)) : resolve(dirname(file), ref);
          if (!existsSync(target)) violations.push({ file: relative(root, file), value: `missing local CSS asset ${ref}` });
        }
      }
    }
  }
}

const distIndex = join(root, "dist", "index.html");
if (existsSync(distIndex)) {
  const html = readFileSync(distIndex, "utf8");
  const refs = [...html.matchAll(/(?:src|href)=["']([^"']+)["']/g)].map((match) => match[1]);
  for (const ref of refs) {
    if (/^(?:data:|#)/.test(ref)) continue;
    if (/^(?:https?:)?\/\//.test(ref)) violations.push({ file: "dist/index.html", value: `external asset ${ref}` });
    else {
      const target = resolve(root, "dist", ref.replace(/^\.\//, "").replace(/^\//, ""));
      if (!existsSync(target)) violations.push({ file: "dist/index.html", value: `missing local asset ${ref}` });
    }
  }
}

if (classified.length) {
  console.log("Classified non-request literals:");
  for (const item of classified) console.log(`  ${item.file}: ${item.value}`);
}
if (violations.length) {
  console.error("Offline frontend audit failed:");
  for (const item of violations) console.error(`  ${item.file}: ${item.value}`);
  process.exit(1);
}
console.log("Offline frontend audit passed: external runtime asset requests = 0");
