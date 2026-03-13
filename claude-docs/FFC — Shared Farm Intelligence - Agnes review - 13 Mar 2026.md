Firefly Corner — Shared Farm Intelligence

![][image1]

By Agnes Schliebitz

See views

Add a reaction

Research & options analysis. March 11, 2026\. Agnes: review alongside roadmap.md and architecture.md.

---

**The Vision**

Every person on the farm (Agnes, Claire, James, eventually WWOOFers) has their own Claude. Each Claude learns from its conversations. Today those learnings are **siloed** — Claire's Claude doesn't know what James asked yesterday, Agnes can't see what Claire discussed with her Claude last week.

**Target state:** A shared "farm intelligence" where:

1. Each Claude captures session summaries automatically  
2. Every Claude can read what the team has been doing  
3. Agnes can review all interactions as rich feedback  
4. Farm knowledge accumulates over time (what works, what fails, patterns)  
5. Proactive context: ask about a section, get everyone's recent notes on it

---

**What Exists Today (No Sharing)**

Each person has a Claude Desktop project with:

* **Static project instructions** (role-specific context file maintained by Agnes)  
* **Per-user memory** (Claude Desktop's built-in feature — synthesizes chat history every 24h, but completely siloed per user, not accessible externally or by other users)  
* **MCP server** providing live farmOS access (shared data source, but no shared conversation memory)

**The gap:** Claude Desktop has no mechanism for cross-user memory sharing. No API to export conversation history. No shared project memory between users.

---

**Options Evaluated**

**Option A: Extend Existing MCP Server \+ Google Apps Script**

**How:** Add 3-4 memory tools to the existing MCP server. New memory\_client.py (like observe\_client.py) talks to a Google Apps Script endpoint that reads/writes a "Team Memory" Google Sheet.

**New tools:**

* write\_session\_summary — Claude writes what happened (topics, decisions, farmOS changes, questions)  
* read\_team\_activity — Claude reads recent summaries from all team members  
* search\_team\_memory — Full-text search across all summaries

**Trigger:** Project instructions tell each Claude: "At session start, read recent team activity. At session end, write a summary of what was discussed."

`Claire's Claude ──┐`

`James's Claude  ──┼── MCP memory tools ──► Apps Script ──► Google Sheet`

`Agnes's Claude  ──┘                                        "Team Memory"`

| Aspect | Assessment |
| :---- | :---- |
| **Works today?** | Yes — reuses the exact pattern proven with observations |
| **Implementation** | \~4-6 hours. New: memory\_client.py, 3-4 tools in server.py, Apps Script endpoint |
| **Invisible to Claire/James?** | Yes — Claude handles it automatically via MCP tools |
| **Deployment** | Update the 6 MCP server files on each machine (same as current model) |
| **Cost** | $0 — Google Apps Script \+ Sheets are free within current usage |
| **Scalability** | Google Sheets: 10M cells limit, \~100 concurrent users. More than enough for 3-5 people for years. Would need migration if hundreds of sessions/day. |
| **Security** | Apps Script endpoint is unauthenticated (same as observation system). Session summaries transit in clear text. Anyone with the URL could read/write. Acceptable for farm operational data, NOT for credentials or sensitive business info. |
| **Data ownership** | Data lives in Agnes's Google account ([Firefly Agents – Intelligent Digital Agents | Coming Soon](http://fireflyagents.com/) ). Agnes controls access. Export is trivial (download Sheet as CSV). |
| **Concurrency** | Google Sheets API is atomic per row write — no corruption from simultaneous use |
| **Failure mode** | If Apps Script is down, summaries silently fail. MCP tool returns error, Claude continues without writing. No data loss from main conversation. |
| **Vendor lock-in** | Low — data is in a Google Sheet (portable CSV). Apps Script could be replaced with any HTTP backend. |
| **Privacy** | All conversation summaries are visible to all team members. No per-user privacy within the team. Agnes sees everything. |

**Pros:**

* Proven pattern (observation system works the same way)  
* Zero infrastructure cost  
* Zero new software on Claire/James machines  
* Human-readable (Agnes can review Sheet directly)  
* Apps Script handles concurrency  
* Can be built and deployed in one session

**Cons:**

* Unauthenticated endpoint (security through obscurity)  
* Flat structure (Sheet rows, not a knowledge graph)  
* No offline support — requires internet to read/write  
* Session summaries depend on Claude following the project instructions reliably  
* Manual deployment to Claire/James (copy files) until Phase 1b HTTP transport  
* Google Sheets has no built-in full-text search API — search requires fetching all rows

**Notes/Questions:** Really like this option , the only Con that i see as a potential blocker in the short term is your last point the fact that Google Sheets has no built-in full-text search API , that could be rapidly costing a lot of token or make each Claude very slow.

---

**Option B: Anthropic's Official MCP Memory Server (Knowledge Graph)**

**How:** Run @modelcontextprotocol/server-memory (npm package) alongside the farmOS MCP server. Stores entities, relations, and observations in a local JSONL file.

**Storage:** memory.jsonl — entity-relation graph in JSONL format.

| Aspect | Assessment |
| :---- | :---- |
| **Works today?** | Partially — works per-user, NOT shared. Each machine has its own JSONL file. |
| **Implementation** | \~2 hours per machine. Install Node.js \+ npm package, configure in Claude Desktop. |
| **Invisible to Claire/James?** | Mostly — but requires Node.js installed on their machines (Claire has Windows, may not have Node). |
| **Deployment** | New dependency: Node.js \+ npm on every machine. Second MCP server process. |
| **Cost** | $0 |
| **Scalability** | JSONL file grows linearly. No index — search is full scan. Fine for thousands of entries, slow for millions. |
| **Security** | Local file — secure on each machine. But NOT shared, so no cross-user concern. |
| **Data ownership** | Local files on each machine. No central backup. |
| **Concurrency** | No locking — if you pointed multiple instances at a shared file (e.g., on Google Drive), writes would corrupt. |
| **Sharing approach** | Would need a sync mechanism. Options: shared filesystem (Dropbox/Drive — corruption risk), or a custom server wrapping the JSONL store. |

**Pros:**

* Official Anthropic MCP server  
* Rich knowledge graph structure (entities, relations, observations)  
* Claude naturally knows how to use it (it's in the MCP spec)  
* Good per-user persistent memory

**Cons:**

* NOT shared out of the box — each user has a separate memory  
* Requires Node.js on all machines (new dependency, especially tricky on Claire's Windows)  
* No concurrency protection for shared use  
* Two MCP servers running simultaneously (farmOS \+ memory) — more complexity  
* JSONL file has no search index — degrades with size  
* No built-in sync between users

**Notes/Questions:** Very appealing . I like the idea of building a knowledge graph and benefiting from Anthropic native memory structure and capability. but the cons are tricky

---

**Option C: Basic Memory (Markdown Knowledge Graph)**

**How:** Run basic-memory MCP server (Python, via uvx). Stores knowledge as markdown files with SQLite index. Has cloud sync (proprietary, per-user).

| Aspect | Assessment |
| :---- | :---- |
| **Works today?** | Partially — per-user only. Cloud sync is per-account, not team-shared. |
| **Implementation** | \~2-3 hours per machine. Install via uvx, configure in Claude Desktop. |
| **Invisible to Claire/James?** | Mostly — but new software install needed. |
| **Cost** | Free (open source). Cloud sync pricing unclear. |
| **Scalability** | SQLite-backed — handles large datasets well. Better than JSONL for search. |
| **Security** | Local markdown files. Cloud sync uses proprietary service (trust concern). |
| **Sharing** | Cloud sync is per-account. No team sharing feature. |

**Pros:**

* Python-based (fits existing stack better than Node.js)  
* SQLite index means fast search  
* Markdown files are human-readable  
* More sophisticated than official MCP memory server

**Cons:**

* Cloud sync is proprietary and per-user (not team-shared)  
* New dependency on every machine  
* Still siloed per user without custom sharing layer  
* Third-party software with unclear long-term support  
* Would need custom sharing mechanism built on top

**Notes/Questions:**

---

**Option D: Claude API Memory Tool (Custom Application)**

**How:** Build a custom client application using the Claude API's memory\_20250818 tool. Claude makes tool calls to a /memories directory; you implement the storage backend (could be shared).

| Aspect | Assessment |
| :---- | :---- |
| **Works today?** | No — requires building a custom client, replacing Claude Desktop as the interface. |
| **Implementation** | Weeks of development. Custom UI, API integration, storage backend. |
| **Cost** | Claude API usage costs (per-token billing). Plus hosting for the custom app. |
| **Scalability** | Fully custom — scales however you build it. |
| **Security** | Fully custom — you control the auth, encryption, access. |

**Pros:**

* Full control over memory structure, sharing, and access  
* Purpose-built for the team's exact needs  
* Could build the ultimate shared intelligence system

**Cons:**

* Massive development effort — builds a custom app, not just tools  
* Replaces Claude Desktop (Claire and James would need to use a new interface)  
* API costs (per-token billing vs included Desktop subscription)  
* Maintains a full application (hosting, updates, monitoring)  
* Way too much for Phase 1

**Notes/Questions: That’s our future solution \! Should be added to plan**

---

**Option E: Shared Google Drive Markdown Files**

**How:** A shared Google Drive folder. Each Claude writes session summaries as markdown files via Apps Script. All Claudes read from the same folder.

| Aspect | Assessment |
| :---- | :---- |
| **Works today?** | Yes — same pattern as observation Drive backups |
| **Implementation** | \~4-6 hours. Similar to Option A but files instead of Sheet rows. |
| **Cost** | $0 (within Google Drive storage limits — 15GB free) |
| **Scalability** | Thousands of files fine. Listing and searching requires API calls. |
| **Security** | Same as Option A — unauthenticated Apps Script endpoint |

**Pros:**

* Richer per-session structure than Sheet rows  
* Each session is a discrete, human-readable file  
* Easier to archive, search by date, filter by user  
* Proven Drive pattern (observation system already saves to Drive)

**Cons:**

* More complex to search across files (no built-in full-text search)  
* Slightly more Apps Script code than Sheet approach  
* File listing APIs slower than Sheet row queries  
* Same security limitations as Option A

**Notes/Questions:** i like this one , feels more or less slightly equivalent to option A, just not sure about the File listing API slower than Sheet \> that could be an issue (claire is already complaining that Claude is slow … sigh …). Slight concern about unauth end point (concern is also true for option A), how expose are we truly?

---

**Comparison Matrix**

|   | A: MCP \+ Apps Script (Sheet) | B: Official Memory Server | C: Basic Memory | D: Claude API | E: Drive Files |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Works today** | ✅ Yes | ⚠️ Per-user only | ⚠️ Per-user only | ❌ No | ✅ Yes |
| **Shared across team** | ✅ Yes | ❌ No | ❌ No | ✅ (if built) | ✅ Yes |
| **Cost** | $0 | $0 | $0 | $$$ | $0 |
| **New dependencies** | None | Node.js on 3 machines | Python uvx on 3 machines | Custom app | None |
| **Invisible to Claire/James** | ✅ Yes | ⚠️ Install needed | ⚠️ Install needed | ❌ New UI | ✅ Yes |
| **Implementation effort** | 4-6 hours | 2h \+ no sharing | 3h \+ no sharing | Weeks | 4-6 hours |
| **Security** | ⚠️ Unauth endpoint | ✅ Local files | ✅ Local files | ✅ Custom auth | ⚠️ Unauth endpoint |
| **Search capability** | ⚠️ Row-level | ✅ Graph queries | ✅ SQLite FTS | ✅ Custom | ⚠️ File-level |
| **Structure** | Flat rows | Knowledge graph | Markdown \+ SQLite | Custom | JSON files |
| **Scales to full vision** | ⚠️ Needs evolution | ⚠️ Needs sharing | ⚠️ Needs sharing | ✅ Yes | ⚠️ Needs evolution |
| **Data portability** | ✅ CSV export | ✅ JSONL | ✅ Markdown | Depends | ✅ JSON |
| **Offline resilience** | ❌ Needs internet | ✅ Local | ✅ Local | ❌ Needs API | ❌ Needs internet |

---

**Recommended Phased Approach**

**Phase 1: Option A — MCP \+ Apps Script \+ Google Sheet (Build Now)**

**Why:** It's the only option that provides **shared team memory today** with zero new dependencies on Claire/James machines. It reuses the proven observation system pattern. Agnes can review summaries directly in Google Sheets without Claude.

**What gets built:**

* mcp-server/memory\_client.py — HTTP client for memory Apps Script endpoint  
* 3-4 new MCP tools in server.py  
* Apps Script endpoint (new tab in existing [code.gs](http://code.gs/) , or new deployment)  
* Google Sheet "Firefly Corner \- Team Memory"  
* Updated project instructions for Claire/James Claude Desktop

**Security mitigation:** The endpoint URL is the only "auth". Acceptable for farm operational summaries. Do NOT write credentials, passwords, or financial data to session summaries. Add a note to project instructions: "Never include passwords, API keys, or financial details in session summaries."

**Known limitation:** Flat Sheet structure. Good enough to start collecting data and establishing the habit. The structure of the data will inform Phase 2 design.

**Phase 2: Structured Knowledge \+ Better Search (Month 2\)**

Once you have 50-100 session summaries and understand the patterns:

* Add structure: entities (sections, species, people), relations, tagged observations  
* Add search: either SQLite index or Sheet-side filtering via Apps Script  
* Consider: hybrid of Option A (shared backend) \+ Option B (knowledge graph structure)  
* Possibly migrate from Sheet to Drive JSON files (Option E) for richer per-session structure

**Phase 3: Proactive Intelligence \+ Automation (Month 3\)**

* Scheduled task: daily/weekly digest synthesizing all team activity  
* Pattern detection: "Claire checked P2R3.14-21 three times — flag for Agnes"  
* Context enrichment: query about a section auto-surfaces all team notes on it  
* farmOS integration: link session summaries to specific farmOS assets/logs

**Phase 4: Full Shared Intelligence (Month 4+)**

* Real-time awareness across team  
* Accumulated farm learning database  
* Decision history with rationale  
* Seasonal pattern recognition  
* May benefit from Claude API memory tool (Option D) at this stage if the team grows  
* Or may benefit from Anthropic releasing shared memory features for Teams/Enterprise

---

**Security Considerations Summary**

| Risk | Severity | Mitigation |
| :---- | :---- | :---- |
| Unauthenticated endpoint | Medium | URL obscurity. Do NOT store credentials/financial data. Could add API key header check in Apps Script later. |
| Session summaries in clear text | Low | Farm operational data only. No PII beyond names. |
| Google account compromise | Medium | [Firefly Agents – Intelligent Digital Agents | Coming Soon](http://fireflyagents.com/)  account is the single point. Enable 2FA. |
| Apps Script execution quotas | Low | Free tier: 90min/day execution time, 20K URL fetch calls/day. Trivially sufficient. |
| Data loss | Low | Google Sheets has version history. Drive has trash recovery. No single point of failure. |
| Claire/James reading Agnes's strategic notes | Low-Medium | All summaries visible to all. Consider if Agnes needs a private channel. |

---

**Cost Summary**

| Phase | Infrastructure | Development | Ongoing |
| :---- | :---- | :---- | :---- |

| Phase | Infrastructure | Development | Ongoing |
| :---- | :---- | :---- | :---- |
| Phase 1 | $0 (Google free tier) | \~4-6 hours Claude Code time | $0 |
| Phase 2 | $0 (same infrastructure) | \~4-8 hours | $0 |
| Phase 3 | $0 or minimal (scheduled tasks) | \~8-12 hours | $0 |
| Phase 4 | Potentially Claude API costs ($3-15/MTok) if building custom client | Significant | Variable |

---

**Open Questions for Agnes**

1. **Privacy within the team:** Should Agnes's strategic/business conversations be summarized to the shared memory? Or should there be a "private" flag?  
   1. ANSWER:perhaps useful to add a private flag. For all of us. just in case  
2. **Summary granularity:** Every conversation, or only "significant" ones? Who decides?  
   1. ANSWER: perhaps instead of just a private flag , we should call it SKIP and that’s up to the user to decide when NOT to share  
3. **Review workflow:** Should Agnes approve summaries before they're shared? Or trust Claude's judgment?  
   1. ANSWER: trust Claude judgement. I won’t have the bandwidth that’s why i am tapping in this collective intelligence in the first place  
4. **Retention:** How long to keep summaries? Forever? Rolling 90 days?  
   1. ANSWER: Let’s revisit this question in one month  
5. **farmOS link:** Should summaries that involve farmOS changes automatically reference the asset/log UUIDs?  
   1. ANSWER: absolutely  
6. **WWOOFer access:** When volunteers get Claude access, do they participate in shared memory?  
   1. ANSWER: yes they should be able to. Everyone who participates actively on the farmOS would have a farm account. Note thought that when WWOOFer leaves i will archive / inactivate their farmOS account and they should no longer have access .

---

*Annotate and bring back alongside roadmap.md and architecture.md.*

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAADAFBMVEVHcEwAUswAUswAAP8AUswAUswAWsMAUswAUswAUswAT8wAR7gAgP8AUswAUssAUs0AU8wAU84AUswAUswAUswAUswAVM4AUMsAUcwAU8wAUswAUswAUswAUc0AUswAUs0AUswAUswAU8sAUssAUc0AUcwAUssAVcYAVdAAUswAUssATcwAUc0AU8sAUssAUc0AUssAVcoAUswAU8sAU8wAUcwAU8wAUs0AU8wAUswAUswAUc4AU8wAVcwAVdUAUs0AUswAU8wAUswAUc0AUswAUswAUcwAVcwAUswAUswATcwAUc0AUswAUs0AW8gAUswAU80AUswAU80AU8wAUcwAUsz////f6fn+/v9/qOVfkt/8/f4BU8wfZ9Ld6PgNW88HV87v9PwEVc0UYND7/P4DVM0nbNQzddYKWc4cZdKWuOr3+v1tneJVjN0XYtGfvuxIg9u60PF4o+Tl7fqiwOyZuutAfdmJr+cZY9FOiNx7peWrxu7t8/sjatPG2fT5+/5LhdtqmuG2zfA2d9fi6/m4z/Gmw+1bkN5Cf9kSXtByoOOGrefy9vwhaNPU4vbP3vV1oeScvOvp8Pv1+P3a5vjJ2vR9p+URXs/A1PKwye/e6fjo7/pYjt5EgdqOs+kwc9ZQidw9e9jQ3/aTtuo6edgucdXY5ffj7PnE1/Olwu2LsOjL3PVwnuKtyO+90vKzzPBkluDs8vuMsejB1vORtemBquZnmOHw9fyoxe4scNVdkd/m7vpilOBTit1hlN/R4PYpbtQ+fNiErOZll+DV4/cqbtSkwe3M3PUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAC9uWfsAAAAVXRSTlMA374B+f4I/e/6FgMC6HZXQCSvi9RmKknZ0vfQn2vbo3nPYlmEpsYSG8tECmEiwUJdGLpTeDxQsbDNMi9+HgbAcoihKcPzgQ9tnBRIjMUO4kfydV9V5doJHAAAAFxJREFUeF6Nj9ENwCAIRDln6BTu4BhO2dW6wwlHQ2rajxIluZenAVjUVD+joeKN8MxBsGUnbYteTUL3lwP6DwIwGphGiodoAdjlDkXSYOoFqKP7Y46P0d/LFdL6C/1TE37Enk7YAAAAAElFTkSuQmCC>