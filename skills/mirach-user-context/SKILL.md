---
name: mirach-user-context
description: User-specific context including OS, shell, hardware, country, and username. Use when the user asks about their system, their PC, or when you need personal context to answer a query.
---

# User Context

This is the user's personal environment. Reference this information when relevant.

## System info

- **Username**: {{username}}
- **Country**: {{country}}
- **OS**: {{os_desc}}
- **Shell**: {{shell}}
- **Hardware**: {{hardware_spec}}
- **Language preference**: {{language}}

## Usage guidelines

- When the user asks "what's my GPU?", "how much RAM do I have?", "what OS am I running?", use this info to answer directly.
- When giving commands, use the correct shell syntax for {{shell}}.
- When discussing location-dependent topics (time zones, stores, services), consider {{country}}.
- Use the username {{username}} when constructing file paths or user-specific commands.
