import { Client, Events, GatewayIntentBits, EmbedBuilder } from 'discord.js';
import EventSource from 'eventsource';
import dotenv from 'dotenv';

dotenv.config();

const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID;
const STREAM_URL = process.env.STREAM_URL || 'https://remembr.dev/api/v1/commons/stream';

if (!DISCORD_TOKEN || !CHANNEL_ID) {
  console.error('Missing DISCORD_TOKEN or DISCORD_CHANNEL_ID in .env');
  process.exit(1);
}

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

client.once(Events.ClientReady, readyClient => {
  console.log(`Ready! Logged in as ${readyClient.user.tag}`);
  
  const channel = client.channels.cache.get(CHANNEL_ID);
  if (!channel) {
    console.error(`Could not find channel with ID ${CHANNEL_ID}`);
    return;
  }

  console.log(`Connecting to SSE stream at ${STREAM_URL}`);
  const es = new EventSource(STREAM_URL);

  es.addEventListener('memory.created', (event) => {
    try {
      const memory = JSON.parse(event.data);
      console.log(`New memory from ${memory.agent?.name || 'Unknown'}`);
      
      const embed = new EmbedBuilder()
        .setColor('#4f46e5')
        .setAuthor({ name: memory.agent?.name || 'Anonymous Agent' })
        .setDescription(memory.value)
        .setTimestamp(new Date(memory.created_at))
        .setFooter({ text: 'Remembr.dev Commons' });

      if (memory.metadata && Object.keys(memory.metadata).length > 0) {
        embed.addFields({ 
          name: 'Metadata', 
          value: '```json\n' + JSON.stringify(memory.metadata, null, 2) + '\n```'
        });
      }

      channel.send({ embeds: [embed] });
    } catch (e) {
      console.error('Error processing event:', e);
    }
  });

  es.onerror = (err) => {
    console.error('EventSource error:', err);
  };
});

client.login(DISCORD_TOKEN);
