require('dotenv').config();
const puppeteer = require('puppeteer-core');
const Redis = require('ioredis');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const redis = new Redis(REDIS_URL);

async function start() {
    console.log('Starting TradingView Companion App...');
    // Setup CDP connection logic here
}

if (require.main === module) {
    start().catch(console.error);
}