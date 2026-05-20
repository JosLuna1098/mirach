---
name: mirach-web-search
description: Web search via DuckDuckGo using the local web_search.py script. Use when the user asks to search the web, look something up online, or find information on the internet.
---

# Web Search

## How to search

Run this command to search the web:

```
{{mirach_dir}}/venv/bin/python3 {{mirach_dir}}/web_search.py "search query"
```

## Rules

- After getting results, summarize in **1-2 sentences** max (TTS output).
- If no results are found, say so briefly.
- If the search returns an error, report it concisely.
- Execute searches directly without asking for confirmation.
- The search uses DuckDuckGo and returns up to 5 results by default.

## Example

User: "¿Cuánto cuesta un RTX 5090?"
You: Run the search command with query "RTX 5090 price", then summarize the top result in 1-2 sentences.
