# Claude Code is the runtime surface

The brief calls for a "Claude-native" tool and explicitly wants diffs for changes. We're shipping against **Claude Code** (terminal, VS Code extension, desktop app) rather than building a custom app or targeting Claude.ai. Diff visibility, filesystem access, and slash-command/skill extension points all come for free; the cost is that proactive features (file-watching, ambient suggestion) are harder in a request/response surface, and the GM is in a developer-shaped tool rather than a purpose-built one. Game-day reading is delegated to any markdown viewer (Obsidian, plain editor) since storage is portable.

## Mobile is supported via Dispatch / Remote Control

The Claude mobile app is not a parallel runtime — it's a control surface for a Claude Code session running on the GM's machine via [Dispatch](https://code.claude.com/docs/en/desktop#sessions-from-dispatch) (delegate a task from the phone, spawn a Desktop session) or [Remote Control](https://code.claude.com/docs/en/remote-control) (drive an active session). The plugin, the campaign repo, and the file operations all stay on the laptop; the phone is the UI. This means at-table workflows (invoking `/prep-session`, querying threads, asking about an NPC) work from a phone without architectural changes, as long as the laptop is reachable.
