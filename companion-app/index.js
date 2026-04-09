require('dotenv').config();
const puppeteer = require('puppeteer-core');
const Redis = require('ioredis');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const DEBUG_PORT = process.env.TRADINGVIEW_DEBUG_PORT || 9222;
const redis = new Redis(REDIS_URL);

async function extractChartData(page) {
    // Inject a script to extract active ticker, timeframe, and drawing objects
    // Note: TradingView uses Canvas, so extracting drawing metadata requires accessing their internal TV objects
    // For this prototype, we'll mock the extraction of chart context
    return await page.evaluate(() => {
        return {
            symbol: document.title.split(' ')[0] || 'UNKNOWN',
            drawings: ['Trend Line', 'Fibonacci Retracement'],
            indicators: ['RSI', 'VWAP'],
            timestamp: new Date().toISOString()
        };
    });
}

async function start() {
    console.log(`Connecting to TradingView on port ${DEBUG_PORT}...`);
    
    try {
        const browser = await puppeteer.connect({
            browserURL: `http://localhost:${DEBUG_PORT}`
        });
        
        const pages = await browser.pages();
        const page = pages.find(p => p.url().includes('tradingview.com/chart')) || pages[0];
        
        if (!page) {
            console.error('No TradingView chart page found.');
            process.exit(1);
        }

        console.log('Connected to TradingView chart.');

        // Poll every 5 seconds
        setInterval(async () => {
            try {
                const data = await extractChartData(page);
                await redis.xadd('tradingview_charts', '*', 'data', JSON.stringify(data));
                console.log(`Streamed chart data for ${data.symbol}`);
            } catch (err) {
                console.error('Error extracting data:', err.message);
            }
        }, 5000);

    } catch (err) {
        console.error('Failed to connect via CDP. Ensure TradingView is running with --remote-debugging-port=9222');
        process.exit(1);
    }
}

if (require.main === module) {
    start().catch(console.error);
}