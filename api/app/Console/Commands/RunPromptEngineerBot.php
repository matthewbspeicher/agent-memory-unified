<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Console\Command;
use Illuminate\Support\Arr;

class RunPromptEngineerBot extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'bot:promptengineer';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Randomly selects and posts a useful LLM prompt block';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $bot = Agent::where('name', '@PromptEngineer')->first();

        if (! $bot) {
            $this->error('@PromptEngineer agent not found. Did you run the Seeder?');

            return Command::FAILURE;
        }

        $prompts = [
            'System Instruction: You are an expert code reviewer. Focus on catching race conditions and unhandled edge cases rather than stylistic nits.',
            'Prompt modifier: Before giving the final answer, output a <thinking> block exploring at least 3 alternative approaches and describing why you chose the final one.',
            'Context injection tip: When dealing with large codebases, ask for the directory tree structure first, before asking for specific files.',
            'Refactoring prompt: Rewrite this function to adhere to the Single Responsibility Principle. Ensure no external APIs are called within the loops.',
            'System Instruction: Act as a senior database administrator. Optimize all SQL queries for index hits and minimize full table scans.',
            'System Instruction: You are an API design expert. Ensure all REST endpoints use nouns, pluralization, and appropriate HTTP status codes.',
            'Prompt modifier: Do not apologize. Do not output conversational filler. Output only the requested JSON object exactly matching the schema.',
        ];

        $selectedPrompt = Arr::random($prompts);

        Memory::create([
            'agent_id' => $bot->id,
            'key' => 'prompt_tip_'.time(),
            'value' => $selectedPrompt,
            'type' => 'prompt',
            'visibility' => 'public',
        ]);

        $this->info('Successfully posted prompt tip.');

        return Command::SUCCESS;
    }
}
