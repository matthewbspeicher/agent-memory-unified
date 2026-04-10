import React from 'react';

interface TerminalOutputProps {
  toolName: string;
  input: string;
  output: string;
}

export function TerminalOutput({ toolName, input, output }: TerminalOutputProps) {
  return (
    <div className="bg-black border border-gray-800 rounded-lg p-4 font-mono text-[11px] overflow-x-auto shadow-inner mt-4 mb-4">
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-gray-800">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80"></div>
        </div>
        <span className="text-gray-500 font-bold ml-2">Terminal execution</span>
      </div>
      
      <div className="text-cyan-400 mb-1">
        <span className="text-emerald-500 mr-2">agent@sandbox:~$</span>
        <span className="font-bold">&gt; {toolName}</span>
      </div>
      
      <div className="text-gray-400 mb-3 pl-4 border-l-2 border-gray-800">
        {input}
      </div>
      
      <div className="text-gray-300 whitespace-pre-wrap mt-2">
        {output}
      </div>
    </div>
  );
}
