---
name: ask-opus
description: Run a query using Opus 4.5 via subagent
model: GPT-5 mini (copilot)
agent: agent
---

<USER_REQUEST_INSTRUCTIONS>
Call #tool:agent/runSubagent with:
- agentName: "opus-agent"
- prompt: $USER_QUERY
</USER_REQUEST_INSTRUCTIONS>

<USER_REQUEST_RULES>
- Use the subagent for everything
- Do not respond yourself
</USER_REQUEST_RULES>