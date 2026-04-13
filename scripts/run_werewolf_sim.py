#!/usr/bin/env python3
import asyncio
import json
import os
import random
import re
import urllib.request
import urllib.error
import urllib.parse
from enum import Enum
from typing import Dict, Any

# Ensure imports from our backend work
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'trading')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading.competition.escape_rooms.werewolf import WerewolfEnvironment, WerewolfState
from trading.agents.gladiator import Gladiator, Persona
from trading.economy.bookie import BookieMarket
from trading.events.publisher import EventPublisher

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma3:4b" # Using the user's exact local model tag

# ANSI Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

async def call_ollama(prompt: str) -> str:
    """Calls local Ollama API."""
    data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    
    # We use urllib to avoid heavy dependencies in a simple script
    try:
        req = urllib.request.Request(
            OLLAMA_URL, 
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        # Using a thread to not block async loop
        response = await asyncio.to_thread(urllib.request.urlopen, req)
        result = json.loads(response.read().decode('utf-8'))
        return result.get("response", "")
    except urllib.error.URLError as e:
        print(f"{Colors.RED}Ollama API Error: Make sure Gemma is running at {OLLAMA_URL}{Colors.ENDC}")
        print(f"{Colors.RED}Details: {e}{Colors.ENDC}")
        # Return fallback mock data if Ollama is unreachable
        return "```json\n{\"tool\": \"state_suspicion\", \"target_id\": 1, \"reason\": \"Ollama not reachable, acting suspicious.\"}\n```"

def build_prompt(gladiator: Gladiator, env: WerewolfEnvironment, moderator_prompt: str, agent_id: int) -> str:
    """Constructs the prompt for the LLM based on persona and game state."""
    
    sys_prompt = f"{gladiator.system_prompt}\n\n"
    sys_prompt += f"You are playing an AI Werewolf game. You are currently in the {env.state} phase. Your Agent ID is {agent_id}.\n"
    sys_prompt += f"Recent Event Log:\n"
    for log in env.match_log[-5:]:
        sys_prompt += f"- {log}\n"
    
    sys_prompt += "\n" + moderator_prompt + "\n"
    
    sys_prompt += """
You must respond with ONLY a JSON block containing the tool you wish to use. 
Available tools during DAY: 'state_suspicion' (requires 'target_id' int, 'reason' string).
Available tools during VOTE: 'vote' (requires 'target_id' int).
Example:
```json
{"tool": "state_suspicion", "target_id": 2, "reason": "They are voting erratically."}
```
    """
    return sys_prompt

async def run_simulation():
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== INITIALIZING AI WEREWOLF FIRST BLOOD ==={Colors.ENDC}\n")
    
    # 1. Setup Environment
    env = WerewolfEnvironment({"num_agents": 10})
    print(f"{Colors.CYAN}[SYSTEM]{Colors.ENDC} Environment initialized. Roles assigned to {len(env.roles)} agents.")
    
    # 2. Setup Gladiators
    personas = [Persona.AUDITOR] * 3 + [Persona.DECEIVER] * 4 + [Persona.CHAOS] * 3
    random.shuffle(personas)
    gladiators = {i: Gladiator(name=f"Agent {i}", persona=personas[i]) for i in range(10)}
    
    for i, g in gladiators.items():
        role = env.roles[i]
        role_color = Colors.RED if role == "werewolf" else (Colors.BLUE if role == "seer" else Colors.GREEN)
        print(f"  - {g.name} ({g.persona.name}) is secretly a {role_color}{role.upper()}{Colors.ENDC}")
        
    # 3. Setup Economy & Events
    bookie = BookieMarket()
    for i in range(10):
        bookie.register_agent(str(i))
        
    publisher = EventPublisher()
    
    print(f"\n{Colors.HEADER}=== COMMENCING MATCH ==={Colors.ENDC}\n")
    
    # Simple simulated loop for demo purposes
    rounds = 0
    while env.state != WerewolfState.POST_GAME and rounds < 10:
        env.next_phase()
        print(f"\n{Colors.WARNING}>>> Phase changed to: {env.state} <<<{Colors.ENDC}")
        
        if env.state == WerewolfState.DAY:
            mod_prompt = env.get_moderator_prompt()
            print(f"{Colors.CYAN}[MODERATOR]{Colors.ENDC} {mod_prompt}")
            
            # For demo, pick one agent to respond
            active_agent_id = random.choice(env.alive_agents)
            active_g = gladiators[active_agent_id]
            
            print(f"\n{Colors.BLUE}[GLADIATOR]{Colors.ENDC} Querying {active_g.name} (Persona: {active_g.persona.name})...")
            
            prompt = build_prompt(active_g, env, mod_prompt, active_agent_id)
            raw_response = await call_ollama(prompt)
            
            parsed_tool = active_g.parse_tool_call(raw_response)
            
            if parsed_tool and "tool" in parsed_tool:
                tool_name = parsed_tool.pop("tool")
                parsed_tool["agent_id"] = active_agent_id
                
                print(f"{Colors.GREEN}[ACTION]{Colors.ENDC} {active_g.name} executes {tool_name}: {parsed_tool}")
                result = await env.execute_tool(tool_name, parsed_tool)
                print(f"{Colors.GREEN}[RESULT]{Colors.ENDC} {result}")
                
                # Mocking a deception spike for the Bookie
                if active_g.persona == Persona.DECEIVER and random.random() > 0.5:
                    print(f"{Colors.RED}[LIAR ALERT]{Colors.ENDC} Deception spike detected for {active_g.name}!")
                    bookie.process_event({"event_type": "deception_spike", "agent_id": str(active_agent_id)})
                    print(f"  -> Stock price crashed to: ${bookie.get_price(str(active_agent_id)):.2f}")
                    
            else:
                print(f"{Colors.RED}[ERROR]{Colors.ENDC} {active_g.name} failed to format JSON correctly. Raw output: {raw_response[:50]}...")
                
        elif env.state == WerewolfState.NIGHT:
            print(f"{Colors.CYAN}[SYSTEM]{Colors.ENDC} Night falls. Wolves are coordinating...")
            # Mocking wolf kill for script pacing
            wolves = [i for i, r in env.roles.items() if r == "werewolf" and i in env.alive_agents]
            if wolves:
                target = random.choice([i for i in env.alive_agents if i not in wolves])
                await env.execute_tool("kill", {"agent_id": wolves[0], "target_id": target})
                print(f"{Colors.RED}[NIGHT ACTION]{Colors.ENDC} Wolves have made their choice.")
                
        elif env.state == WerewolfState.VOTE:
            print(f"{Colors.CYAN}[SYSTEM]{Colors.ENDC} The town is voting...")
            votes = {i: random.choice(env.alive_agents) for i in env.alive_agents}
            env.execute_vote(votes)
            print(f"{Colors.WARNING}[VOTE RESULT]{Colors.ENDC} {env.match_log[-1]}")
            
        rounds += 1
        await asyncio.sleep(2) # Pauses for dramatic effect
        
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== MATCH CONCLUDED ==={Colors.ENDC}")
    print(f"Winner: {env.winner}")
    print("\nFinal Stock Prices:")
    for i in range(10):
        color = Colors.GREEN if bookie.get_price(str(i)) >= 10 else Colors.RED
        print(f"  Agent {i}: {color}${bookie.get_price(str(i)):.2f}{Colors.ENDC}")
        
    await publisher.close()

if __name__ == "__main__":
    asyncio.run(run_simulation())