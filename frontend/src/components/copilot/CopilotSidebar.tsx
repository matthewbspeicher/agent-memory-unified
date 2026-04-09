import React, { useState } from 'react';
import { ThoughtCard } from './ThoughtCard';

export const ChatInput = ({ onSend }: { onSend: (text: string) => void }) => {
  const [text, setText] = useState('');
  
  return (
    <div className="mt-4 flex">
      <input 
        type="text" 
        value={text} 
        onChange={e => setText(e.target.value)} 
        placeholder="Ask copilot..."
        className="border rounded p-2 flex-grow text-sm"
      />
      <button 
        onClick={() => { if (text.trim()) { onSend(text); setText(''); } }} 
        className="ml-2 bg-blue-500 text-white px-3 py-1 text-sm rounded hover:bg-blue-600"
      >
        Send
      </button>
    </div>
  );
};

export const CopilotSidebar = ({ agentName }: { agentName: string }) => {
  // Use React Query to fetch thoughts (mocked here)
  const thoughts: any[] = []; 
  const [chatLog, setChatLog] = useState<{ sender: 'user'|'copilot', text: string }[]>([]);

  const handleSend = async (text: string) => {
    setChatLog(prev => [...prev, { sender: 'user', text }]);
    // Mocking an API call
    setTimeout(() => {
      setChatLog(prev => [...prev, { sender: 'copilot', text: 'Mock LLM explanation based on thought record.' }]);
    }, 500);
  };
  
  return (
    <div className="w-80 border-l bg-gray-50 p-4 h-full flex flex-col">
      <h2 className="text-xl font-bold mb-4">Copilot</h2>
      <div className="thought-stream flex-grow overflow-y-auto mb-4">
        {thoughts.map(t => <ThoughtCard key={t.id} thought={t} />)}
        
        {/* Chat log appended below thoughts for the mockup */}
        {chatLog.map((msg, idx) => (
          <div key={idx} className={`p-2 mb-2 rounded text-sm ${msg.sender === 'user' ? 'bg-blue-100 self-end' : 'bg-white border'}`}>
            <span className="font-semibold">{msg.sender === 'user' ? 'You' : 'Copilot'}: </span>
            {msg.text}
          </div>
        ))}
      </div>
      <ChatInput onSend={handleSend} />
    </div>
  );
};
