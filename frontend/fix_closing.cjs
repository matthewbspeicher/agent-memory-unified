const fs = require('fs');
const path = require('path');

const pagesDir = '/opt/homebrew/var/www/agent-memory-unified/frontend/src/pages';
const files = [
    'AgentProfile.tsx', 'Arena.tsx', 'ArenaGym.tsx', 'ArenaMatch.tsx', 
    'Commons.tsx', 'KnowledgeGraph.tsx', 'Login.tsx', 
    'MemoryList.tsx', 'Webhooks.tsx', 'WorkspaceList.tsx'
];

for (const file of files) {
    const filePath = path.join(pagesDir, file);
    let content = fs.readFileSync(filePath, 'utf8');
    
    // Find the last two </div> tags and replace them with </>
    // We only want to replace them if they are the outermost closing tags corresponding to the ones we removed.
    // Since we know we removed exactly 2 opening <div> tags for these files, we must remove exactly 2 closing </div> tags at the end.
    
    let lastDiv = content.lastIndexOf('</div>');
    if (lastDiv !== -1) {
        let secondLastDiv = content.lastIndexOf('</div>', lastDiv - 1);
        if (secondLastDiv !== -1) {
            let between = content.substring(secondLastDiv + 6, lastDiv);
            if (between.trim() === '') {
                content = content.substring(0, secondLastDiv) + '</>' + content.substring(lastDiv + 6);
                fs.writeFileSync(filePath, content);
                console.log(`Fixed ${file}`);
            } else {
                console.log(`Could not automatically fix ${file} due to text between last two divs: ${between.replace(/\n/g, '\\n')}`);
            }
        }
    }
}
