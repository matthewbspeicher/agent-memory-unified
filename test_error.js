const fs = require('fs');
const history = JSON.parse(fs.readFileSync('/opt/agent-memory-unified/.pi/batch-history.json', 'utf8'));
const last = history[history.length - 1];
console.log(JSON.stringify(last.errors, null, 2));
