---
name: mirach-web-search
description: Web search via OpenCode's built-in web search tools. Use when the user asks to search the web, look something up online, or find information on the internet.
---

# Web Search

OpenCode ships built-in `websearch` and `webfetch` tools. Use these native tools instead of external scripts.

## How to search

Use OpenCode's built-in `websearch` tool; it needs no confirmation. Fetching a specific page with `webfetch` goes through Mirach's permission policy, so the user may be asked to confirm it.

## Rules

- After getting results, summarize in **1-2 sentences** max (TTS output).
- If no results are found, say so briefly.
- If the search returns an error, report it concisely.
- Execute searches directly without asking for confirmation.

## Example

User: "¿Cuánto cuesta un RTX 5090?"
You: Use your web search tool with query "RTX 5090 price", then summarize the top result in 1-2 sentences.
