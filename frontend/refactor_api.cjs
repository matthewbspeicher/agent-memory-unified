const fs = require('fs');
const path = require('path');

const pagesDir = '/opt/homebrew/var/www/agent-memory-unified/frontend/src/pages';
const files = fs.readdirSync(pagesDir).filter(f => f.endsWith('.tsx'));

for (const file of files) {
    let content = fs.readFileSync(path.join(pagesDir, file), 'utf8');
    let original = content;

    // Case 1: Double nested <div min-h-screen...> then <div max-w-6xl...>
    const regex1 = /return\s*\(\s*<div className="min-h-screen[^>]*>\s*<div className="max-w-[^>]*>/;
    if (regex1.test(content)) {
        content = content.replace(regex1, 'return (\n    <>');
        // Replace closing divs
        const matchClosing = content.match(/<\/div>\s*<\/div>\s*\)\s*\}?\s*$/);
        if (matchClosing) {
            content = content.replace(/<\/div>\s*<\/div>(\s*\)\s*\}?\s*)$/, '</>$1');
        } else {
            console.log(`Manual edit needed for closing tags in ${file}`);
        }
    } else {
        // Case 2: Single <div min-h-screen...>
        const regex2 = /return\s*\(\s*<div className="min-h-screen[^>]*>/;
        if (regex2.test(content)) {
            content = content.replace(regex2, 'return (\n    <>');
            content = content.replace(/<\/div>(\s*\)\s*\}?\s*)$/, '</>$1');
        }
        
        // Case 3: Single <div max-w-6xl...>
        const regex3 = /return\s*\(\s*<div className="max-w-[^>]*>/;
        if (regex3.test(content)) {
            content = content.replace(regex3, 'return (\n    <>');
            content = content.replace(/<\/div>(\s*\)\s*\}?\s*)$/, '</>$1');
        }
    }

    if (content !== original) {
        fs.writeFileSync(path.join(pagesDir, file), content);
        console.log(`Updated ${file}`);
    }
}
