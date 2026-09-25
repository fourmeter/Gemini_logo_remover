import re

with open('build.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Make context creation conditional

# userscriptCtx
content = re.sub(
    r'(const userscriptCtx = await esbuild\.context\({)',
    r'let userscriptCtx = null;\nif (existsSync("src/userscript/index.js")) {\n  userscriptCtx = await esbuild.context({',
    content
)
content = re.sub(
    r'(    __GWR_AUTO_INIT_USERSCRIPT__: \'true\'\n  }\n\}\);)',
    r'\g<1>\n}',
    content
)

# extensionMainCtx
content = re.sub(
    r'(const extensionMainCtx = await esbuild\.context\({)',
    r'let extensionMainCtx = null;\nif (existsSync("src/extension/contentMain.js")) {\n  extensionMainCtx = await esbuild.context({',
    content
)
content = re.sub(
    r'(    __GWR_AUTO_INIT_USERSCRIPT__: \'false\'\n  }\n\}\);)',
    r'\g<1>\n}',
    content
)

# extensionIsolatedCtx
content = re.sub(
    r'(const extensionIsolatedCtx = await esbuild\.context\({)',
    r'let extensionIsolatedCtx = null;\nif (existsSync("src/extension/isolatedBridge.js")) {\n  extensionIsolatedCtx = await esbuild.context({',
    content
)
content = re.sub(
    r'(  minify: isProd\n\}\);)',
    r'\g<1>\n}',
    content,
    count=1
) # We need to be careful with this match because it applies to both isolated and service worker. Wait, I'll match the exact names.

# Actually, I can just use python string replacement.

content = content.replace(
    "const extensionIsolatedCtx = await esbuild.context({",
    "let extensionIsolatedCtx = null;\nif (existsSync('src/extension/isolatedBridge.js')) {\n  extensionIsolatedCtx = await esbuild.context({"
)

content = content.replace(
    "  minify: isProd\n});\n\nconst extensionServiceWorkerCtx = await esbuild.context({",
    "  minify: isProd\n});\n}\n\nlet extensionServiceWorkerCtx = null;\nif (existsSync('src/extension/serviceWorker.js')) {\n  extensionServiceWorkerCtx = await esbuild.context({"
)

content = content.replace(
    "  minify: isProd\n});\n\nconsole.log(`🚀",
    "  minify: isProd\n});\n}\n\nconsole.log(`🚀"
)

# Fix Promise.all calls for rebuild and watch

rebuild_list = """  await Promise.all([
    
    videoWebsiteCtx.rebuild(),
    workerCtx.rebuild(),
    userscriptCtx?.rebuild(),
    extensionMainCtx?.rebuild(),
    extensionIsolatedCtx?.rebuild(),
    extensionServiceWorkerCtx?.rebuild()
  ].filter(Boolean));"""

content = re.sub(
    r'  await Promise\.all\(\[\s+videoWebsiteCtx\.rebuild\(\),\s+workerCtx\.rebuild\(\),\s+userscriptCtx\.rebuild\(\),\s+extensionMainCtx\.rebuild\(\),\s+extensionIsolatedCtx\.rebuild\(\),\s+extensionServiceWorkerCtx\.rebuild\(\)\s+\]\);',
    rebuild_list,
    content
)

watch_list = """  await Promise.all([
    
    videoWebsiteCtx.watch(),
    workerCtx.watch(),
    userscriptCtx?.watch(),
    extensionMainCtx?.watch(),
    extensionIsolatedCtx?.watch(),
    extensionServiceWorkerCtx?.watch()
  ].filter(Boolean));"""

content = re.sub(
    r'  await Promise\.all\(\[\s+videoWebsiteCtx\.watch\(\),\s+workerCtx\.watch\(\),\s+userscriptCtx\.watch\(\),\s+extensionMainCtx\.watch\(\),\s+extensionIsolatedCtx\.watch\(\),\s+extensionServiceWorkerCtx\.watch\(\)\s+\]\);',
    watch_list,
    content
)


with open('build.js', 'w', encoding='utf-8') as f:
    f.write(content)
