---
name: mirach-web-search
description: Web search via OpenCode's built-in web search tools. Use when the user asks to search the web, look something up online, or find information on the internet.
---

# Web Search

OpenCode has built-in web search capabilities available through the `--dangerously-skip-permissions` flag. Use these native tools instead of external scripts.

## How to search

Use OpenCode's built-in web search tool. The daemon already runs with `--dangerously-skip-permissions`, so the search tool is available without asking.

## Rules

- After getting results, summarize in **1-2 sentences** max (TTS output).
- If no results are found, say so briefly.
- If the search returns an error, report it concisely.
- Execute searches directly without asking for confirmation.

## Example

User: "¿Cuánto cuesta un RTX 5090?"
You: Use your web search tool with query "RTX 5090 price", then summarize the top result in 1-2 sentences.
