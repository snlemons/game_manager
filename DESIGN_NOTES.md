# Design Brief: Claude-Native TTRPG Campaign Organization Tool

This system will be a Claude-native system for managing information about my RPG campaigns as a GM, and for planning new things based on that existing information. I'm thinking about things like plot lines, regions, characters (PCs and NPCs), items, themes, and maybe other things. I'd like the files to be organized in relatively human-readable ways so a user can inspect and modify them directly if they want. It should work well with Claude and Claude Code, doing things like showing diffs for changes made. The player should be able to ingest other resources like game module documents or setting resources to integrate them into the plans.

## What you're building against

The TTRPG campaign organization space is crowded but unsatisfying. Every existing tool sits somewhere on a spectrum between "blank canvas with steep learning curve" (Obsidian) and "opinionated structure that fights your creative process" (RPG Manager, World Anvil). The dominant DIY pattern — Obsidian with markdown files and `[[wiki links]]` — has roughly 19% of the GM market by community polling, and it wins not because it's TTRPG-specific but because it's a flexible note system GMs bend to their needs.

The opening for a Claude-native tool isn't to be a better Obsidian or a prettier Notion. It's to do things those tools structurally cannot: understand the content of campaign notes, surface connections proactively, and reduce the maintenance overhead that kills most GM organization systems within three sessions.

## Core principles to design around

**Notes serve the GM, not the other way around.** Mike Shea's framing in "Organizing Your RPG Prep Notes" is the most important piece of received wisdom in this space. The most common failure mode of GM organization tools is that they require so much upfront structure and ongoing maintenance that they become a second job. Any feature that demands the GM categorize, tag, or fill out template fields before they can capture an idea is a feature that will eventually be abandoned. Default to capture-now-structure-later.

**Linking matters more than folders.** This is the consensus across every Obsidian-based workflow. Folders are visual reassurance; links are what make the system useful months later when a player asks "what happened to Rulf from three years ago?" Build link suggestion and automatic backlinking as first-class features. A Claude-native tool can do something Obsidian can't: suggest links by understanding content, not just literal name matches.

**Separate reference notes from session plans.** This is the cleanest distinction in the Obsidian TTRPG Tutorials material. Reference notes (NPCs, locations, monsters, items, factions) are static and get linked to. Session plan notes are navigational and ephemeral — they point at reference notes and get archived as session logs after play. Make this distinction visible in the UI and let it shape how the agent suggests where new content should live.

**Most GMs don't need most features.** Sly Flourish's "junk drawer" folder for "campaign support" is a tell: experienced GMs eventually learn that most categorization schemes are aspirational. A single NPCs page with one-line entries is what he actually uses, not an NPC database with twelve fields per character. Default to minimal structure. Let GMs add complexity if they want it, but don't ship a tool that demands it.

## Recommended structure (the shipping default)

```
Campaign/
├── Characters (single page, one section per PC)
├── NPCs (single page, current and past)
├── Sessions/
│   └── YYYY-MM-DD Session N.md (date-prefixed for sort order)
├── Maps/
├── Locations (optional, only if the campaign needs it)
├── Factions (optional, only if the campaign needs it)
└── Campaign Support/ (the junk drawer)
```

This mirrors Shea's structure deliberately. It's flat enough that nothing's more than two clicks from anywhere, and it scales by accretion rather than upfront planning. The optional folders should not appear until the GM creates content that wants to live there — don't ship an empty Factions folder begging to be filled.

For multi-campaign setups, support a shared "Atlas" or "Setting" space outside any individual campaign, following the pattern from phd20.com's setup. World details (gods, regions, calendar, shared NPCs) live there and get linked into campaigns. Don't duplicate.

## What Claude-native should actually mean

Most "AI campaign tools" currently on the market (Saga20, Archivist, RollSummary) are transcription-and-summarization layers that bolt onto external storage. That's the wrong ambition. The right ambition is an agent that lives inside the GM's organizational system and reduces the work of running it.

Concrete capabilities that justify being Claude-native:

**Capture from messy input.** Let the GM paste a wall of session notes, a rambling voice memo transcript, or a half-finished prep doc and have the agent extract entities (NPCs, locations, items, plot threads), reconcile them with existing notes, and propose where to file new content. The GM approves changes; nothing gets written without confirmation.

**Pre-session prep assistance.** Before a session, the agent should be able to pull together a one-page brief: recap of last session, active plot threads, NPCs the party might encounter, locations they're heading toward, unresolved consequences, items they're carrying that might matter. This is the highest-value workflow because it's the work GMs most often skip when busy, and it's the work that most determines session quality.

**Continuity catching.** "You said three sessions ago that this NPC was dead." "The party already has a key to this door." "This faction is supposed to be hostile to that one." A tool that understands the content can flag contradictions before they happen at the table.

**Lazy entity creation.** When the GM writes "Sera the blacksmith mentioned the mines were closed" in a session note, the agent should offer to create an NPC entry for Sera (one line, expandable later) and a location entry for the mines, with bidirectional links. The GM presses one button; they don't fill out a form.

**Thread and consequence tracking.** This is what Sessionbound is trying to do and what most tools miss. Every session generates open threads ("they promised to deliver the letter") and concrete consequences ("the guard captain owes them a favor"). These should be first-class objects that show up in pre-session briefs and decay if not addressed.

**Cross-session search by meaning, not keyword.** "When did the party last interact with the Veiled Court?" should work even if some session notes call it "the Court," some call it "those masked weirdos," and some just describe a meeting without naming the faction.

## What to deliberately not build

**Don't build a worldbuilding tool.** World Anvil and LegendKeeper occupy that space; trying to compete there will pull the design toward heavy upfront structure. Worldbuilding lives in setting notes that the campaign tool links to, not in the campaign tool itself.

**Don't build a VTT or initiative tracker.** Foundry, Roll20, and others own table-side play. The tool is for prep and continuity, not for running combat.

**Don't build stat block management.** Plugins like Fantasy Statblocks handle this in Obsidian; baking rules-system-specific features in will turn into perpetual maintenance across D&D editions, Pathfinder, Call of Cthulhu, and the long tail. Stay system-agnostic and let GMs link out to their reference of choice.

**Don't build collaborative real-time editing for players.** Critical Notes does this; it's a different product. A GM tool that includes a player-facing view (export-only, with secrets redacted) is fine. Real-time multiplayer is not.

**Don't impose entity schemas.** RPG Manager requires everything to be an "element" of a specific type. This is exactly the rigidity that makes tools feel like a second job. NPCs can be one-line entries or two-page biographies; the system should accommodate both without demanding the GM declare which.

## File format and portability

Use Markdown with frontmatter for storage. This is non-negotiable for two reasons: GMs have been burned by tools that disappeared (campaigns trapped in proprietary formats are a recurring lament in TTRPG communities), and Markdown is the lingua franca of the Obsidian-using GM population, which is the most likely audience. Anything the tool produces should be readable in any text editor and importable into Obsidian.

The `[[wiki link]]` syntax is the established convention; use it. Don't invent a new linking syntax.

## Onboarding shape

Most GMs evaluating organization tools have an existing campaign in some other system. The first-run experience should assume they're migrating, not starting fresh. "Paste or upload your existing notes, and I'll propose a structure" is a better cold start than a blank vault. Be aggressive about extracting structure from messy input — that's the demonstration of value that justifies switching.

The other large segment is GMs starting a new campaign. For them, offer a guided setup that asks just enough questions to scaffold the first session: what system, who's in the party (names and one-line concepts), what's the opening scene. Don't ask about factions, world history, or magic systems. Those will emerge through play.

## Reference materials the building agent should consume

The most useful primary sources, in priority order:

1. Sly Flourish, "Organizing Your RPG Prep Notes" (https://slyflourish.com/organizing_notes.html) — the philosophical foundation.
2. Sly Flourish, "Using Obsidian for Lazy RPG Prep" (https://slyflourish.com/obsidian.html) — practical implementation.
3. Obsidian TTRPG Tutorials, Vault Structure page — the most-thought-through community structure.
4. GM Assistant blog, "Using Obsidian for D&D and TTRPG Notes" — useful for understanding what GMs actually do with these tools day to day.
5. The Sessionbound itch.io page — read this to understand the Pre/During/Post session workflow framing, which is the right operational model.

Read all five before making structural decisions. The patterns that show up in multiple sources are the ones to honor; the patterns unique to a single source are usually that author's idiosyncratic preference.

## The test of success

A GM who has used the tool for ten sessions should be able to answer this question in under thirty seconds: "What's the last thing the party did involving Sera the blacksmith?" If they have to search, scroll, or remember which folder Sera lives in, the tool has failed. If the agent surfaces the answer with the relevant session excerpt and the current state of the relationship, it has done what no existing tool does.