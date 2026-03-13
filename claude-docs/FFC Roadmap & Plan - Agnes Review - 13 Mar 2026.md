Firefly Corner — Roadmap & Plan

![][image1]

By Agnes Schliebitz

See views

Add a reaction

As of March 11, 2026\. Agnes: annotate this doc and bring back to discuss.

---

**Completed Phases**

**Phase 0: Landcare Demo (March 7–10, 2026\) ✅**

* 75 HTML pages (37 view \+ 37 observe \+ 1 index) for all 5 paddock 2 rows  
* QR codes generated and printed for all 37 sections  
* Live farmOS import: 404 plant assets, 442 observation logs, 0 failures  
* Pipeline: fieldsheets → parse → sections.json → generate → GitHub Pages

**Phase 0.5: Plant Types Foundation (March 5–6, 2026\) ✅**

* plant\_types.csv v7: 218 records, 17 columns, farmos\_name as canonical key  
* farmOS taxonomy: 223 plant types (218 CSV \+ 5 field observation additions)  
* v6→v7 migration: 16 renames, 15 archives, 157 creates

**Phase A: Field Observation System (March 7–9, 2026\) ✅**

* observe.js: vanilla JS forms (Quick Report, Full Inventory, Section Comment, Add New Plant)  
* Apps Script backend: Sheet append \+ Drive JSON save  
* 86 real field observations from Claire, James, Hadrien  
* 131 approved and imported to farmOS (64 inventory updates, 11 new plants, 5 new types)  
* Review workflow: pending → reviewed → approved → imported (+ rejected)

**Phase H1: Historical Log Import (March 9, 2026\) ✅**

* 422 backdated logs from Claire's renovation spreadsheets  
* R1-R3: 392 logs | R4/R5: 30 logs  
* 201 dead/removed plants identified (no farmOS assets yet — Phase H2)

**Phase 1a: farmOS MCP Server — Local STDIO (March 9–11, 2026\) ✅**

* 13 tools (6 read \+ 4 write \+ 3 observation management)  
* 5 resources, 3 prompts  
* Deployed to Agnes (macOS), Claire (Windows), James (macOS)  
* Error handling fix March 11: raises on auth failures instead of silent empty results

**Section ID Verification (March 11, 2026\) ✅**

* All 37 active farmOS section IDs match QR page IDs exactly  
* Data integrity verified: 414 plants \+ 1033 logs, 0 mismatches  
* No QR reprinting needed

---

**Current State — What Works Today**

| Capability | Status | How |
| :---- | :---- | :---- |
| View planted sections | ✅ Working | QR code → GitHub Pages landing page |
| Log field observations | ✅ Working | QR observe page → Apps Script → Google Sheet |
| Query farmOS (plants, sections, logs) | ✅ Working | Claude Desktop \+ MCP server (local) |
| Create observations/activities in farmOS | ✅ Working | Claude Desktop \+ MCP server |
| Review & import observations to farmOS | ✅ Working | Claude Desktop \+ MCP tools |
| Generate pages from farmOS | ✅ Working | export\_farmos.py → generate\_site.py |

---

**Next Priorities — Short Term**

**1\. MCP Server Deployment to Claire & James**

*  Copy updated farmos\_client.py to both machines (error handling fix)  
*  James: \~/firefly-mcp/ on Mac  
*  Claire: C:\\firefly-mcp\\ on Windows  
*  Both restart Claude Desktop after update  
* **Notes/Questions:** DONE. Need to add Olivier on PC

**2\. Password Rotation**

*  Rotate James's farmOS password (exposed during setup)  
*  Rotate Claire's farmOS password (exposed during setup)  
*  Update env vars in their Claude Desktop configs  
* **Notes/Questions:** DONE

**3\. Media Management Strategy**

*  Photos currently go to Google Drive only (not farmOS)  
*  Decision needed: farmOS file upload? Keep Drive? Both?  
*  farmOS supports binary POST for file uploads (image field on all assets/logs)  
*  Architecture question: photos on observations → which farmOS log?  
* **Notes/Questions:**  
  * farmOS file upload & keep on drive for now.  
  * if the photo is attached to an observation on a specific plant asset than the photo needs to be attached to the plant asset, and rename to photo with the observation log name

---

**Medium Term — Weeks 2–4**

**Phase 1b: MCP Server HTTP Transport**

*  Move from local STDIO to remote HTTP server  
*  Removes need to copy files to each machine  
*  Single server, all users connect remotely  
*  API key or OAuth2 auth for MCP connections  
*  Where to host? (VPS, Cloudflare Worker, farm server?)  
* **Notes/Questions:** Agree that this is a hot priority but i would rather continue iterating on the prototype with feedback from all current users, especially from Claire and Olivier who are on the farm for a few more days. But they are leaving to Europe next week Saturday at that point i won’t be able to maintain their local MCP SO we need to at that point have switch to the remote MCP

**Phase B: Observe Page Enhancements**

*  Photo compression improvements (currently 1200px max, 0.7 JPEG)  
*  Audio recording for voice observations  
*  Offline queue with IndexedDB (currently localStorage, media stripped offline)  
* **Notes/Questions:** Yes to all that

**Phase H2: Dead Plant Assets**

*  Create farmOS assets for 201 historical dead/removed plants  
*  These exist in renovation spreadsheets but have no farmOS representation  
*  Low priority — historical completeness, not operational need  
* **Notes/Questions**: Even if lower priority it is still absolutely required so we can completely archive the spreadsheet. We need all that data for analysis. So should still be in the plan

**Phase 2: Claire's First Real Log**

*  Claire uses Claude \+ MCP in natural language to log a field activity  
*  "I watered P2R3 today" → activity log in farmOS  
*  "P2R2.3-9 pigeon pea now has 3, lost 2 to frost" → observation log  
*  Validates the "Claude IS the UI" architecture decision  
* **Notes/Questions:** Yes but first check my braindump related to farmOS:we need to maximise use of existing farmOS capability here, especially the log entity capability : log type/category/ownership/status/etc.

---

**Longer Term — Months 2–3**

**Phase 3: Nursery & Seed Bank**

*  Import 244 seed records from seed\_bank.csv as farmOS Seed assets  
*  Implement native Seed→Plant lifecycle workflow  
*  Nursery shelf location tracking (Structure assets exist: 17\)  
*  Seed germination tracking  
* **Notes/Questions:** THIS NOT LONG TERM . This is immediate in parallel activity this week, as James and Agnes need to take over the operation when Claire and Olivier leave at the need of next weekthat Claire and Olivier are working on with their claude to prepare details requirement . Will need to be in the prototype

**Site Regeneration Automation**

*  Currently manual: run export → generate → push  
*  Could be triggered by farmOS webhook or scheduled task  
*  Or run on-demand via Claude when data changes  
* **Notes/Questions:** YES. And as per brain dump on leveraging farmOS: make use of existing workflow/approval flow capability in farmOS (log ownership and status)

**Harvest Tracking**

*  2–3 months of WhatsApp harvest data (summer 2025/2026)  
*  Parse: "3kg tomatoes from P1R1" → farmOS harvest log  
*  Need WhatsApp export or structured capture going forward  
* **Notes/Questions:** there is not only harvest of fruits and vegetable (generic category for this type of harvest would be food harvest) , there is even a more fundamental harvest which is harvest of seeds which goes then into the seed bank . That is a key operational flow that we do today. Currently the food harvest are reported in our whatsapp group I need you to propose a way to extract the data. And then we need a new app flow with QR code / HTML form on mobile for harvest

---

**Long Term — Month 3+**

**Phase 4: farm\_syntropic Drupal Module**

*  Custom farmOS module with proper fields on plant\_type taxonomy  
*  Strata, succession\_stage, plant\_functions as structured data (not in descriptions)  
*  New taxonomies: strata, succession\_stage, plant\_function  
*  New asset types: Consortium  
*  New log types: Pruning, Biomass  
*  Data migration from current description text to structured fields  
* **Notes/Questions:** Agree this is later BEFORE that phase i want that we have a local FarmOS docker setup and also consider our own hosting on Railways

**Phase 5: Multi-User & Advanced AI**

*  Shared Claude Project for the team (when available)  
*  Voice input for field use  
*  Live site updates from farmOS data changes  
*  Knowledge base evolution (which consortiums work, yield patterns)  
*  WhatsApp integration for harvest logs  
* **Notes/Questions: The “**WhatsApp integration for harvest logs” shoudl not be required in the future once we move to  QRcode \> mobile html experience . Also want to consider that we have our own agentic experience for all users , talk to AI / ask question etc. Look at my brain dump for some of my thoughts on that. Also integration Paddock 1 is ALSO SUPER URGENT and need to be done in parallel next week. IT should be easier and faster because Paddock 1 subsections are already designed and in farmOS, the field sheets are mostly up to date and most of the plants should match our Plant types. so it is a matter of analysing the field sheets, generating the QR code and then pushing to farmOS and generate HTML

---

**Not Planned / Deferred**

| Item | Why Deferred |
| :---- | :---- |

| Item | Why Deferred |
| :---- | :---- |
| Custom mobile app | Claude mobile IS the app |
| Multi-agent orchestration | One good agent first |
| Custom farmOS dashboards | Use API, not UI |
| Weather integration | Nice-to-have, not critical |
| Automated notifications | Need use cases first |
| P1 (Paddock 1\) data | Focus on P2 first |

---

**Open Questions**

1. **HTTP transport hosting** — Where should the central MCP server live?  
   1. ANSWER: Railways is my preference . We are already using railways for Firefly Agents MCP servers.  
2. **Media strategy** — Google Drive vs farmOS vs both for photos?  
   1. ANSWER: both. FarmOS for structured data \+ photo for plant asset from observation. Google Drive for unstructured data and all media: documents, how to guides, videos  and complete photo library  
3. **Site regeneration trigger** — Manual, webhook, or scheduled?  
   1. ANSWER: probably webhook  
4. **P1 data** — When do we start tracking Paddock 1?  
   1. ANSWER: Immediate priority in parallel with continuous improvement on field operation with current prototype, nursery and seed bank flows ,  compost flow.  
5. **Volunteer access** — How do WWOOFers interact beyond QR pages?  
   1. ANSWER: each WWOOFER  also has a farmOS user so should be able to use Claude. Ideally Claude mobile or own AI agent app which means linked to remote farmOS MCP access  
6. **Harvest capture** — WhatsApp parsing vs structured input form?  
   1. ANSWER: structure input form similar to QR landing page experience. Once we migrated current harvest data from WhatsApp

---

*Annotate this document and bring back to discuss priorities and decisions.*

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAADAFBMVEVHcEwAUswAUswAAP8AUswAUswAWsMAUswAUswAUswAT8wAR7gAgP8AUswAUssAUs0AU8wAU84AUswAUswAUswAUswAVM4AUMsAUcwAU8wAUswAUswAUswAUc0AUswAUs0AUswAUswAU8sAUssAUc0AUcwAUssAVcYAVdAAUswAUssATcwAUc0AU8sAUssAUc0AUssAVcoAUswAU8sAU8wAUcwAU8wAUs0AU8wAUswAUswAUc4AU8wAVcwAVdUAUs0AUswAU8wAUswAUc0AUswAUswAUcwAVcwAUswAUswATcwAUc0AUswAUs0AW8gAUswAU80AUswAU80AU8wAUcwAUsz////f6fn+/v9/qOVfkt/8/f4BU8wfZ9Ld6PgNW88HV87v9PwEVc0UYND7/P4DVM0nbNQzddYKWc4cZdKWuOr3+v1tneJVjN0XYtGfvuxIg9u60PF4o+Tl7fqiwOyZuutAfdmJr+cZY9FOiNx7peWrxu7t8/sjatPG2fT5+/5LhdtqmuG2zfA2d9fi6/m4z/Gmw+1bkN5Cf9kSXtByoOOGrefy9vwhaNPU4vbP3vV1oeScvOvp8Pv1+P3a5vjJ2vR9p+URXs/A1PKwye/e6fjo7/pYjt5EgdqOs+kwc9ZQidw9e9jQ3/aTtuo6edgucdXY5ffj7PnE1/Olwu2LsOjL3PVwnuKtyO+90vKzzPBkluDs8vuMsejB1vORtemBquZnmOHw9fyoxe4scNVdkd/m7vpilOBTit1hlN/R4PYpbtQ+fNiErOZll+DV4/cqbtSkwe3M3PUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAC9uWfsAAAAVXRSTlMA374B+f4I/e/6FgMC6HZXQCSvi9RmKknZ0vfQn2vbo3nPYlmEpsYSG8tECmEiwUJdGLpTeDxQsbDNMi9+HgbAcoihKcPzgQ9tnBRIjMUO4kfydV9V5doJHAAAAFxJREFUeF6Nj9ENwCAIRDln6BTu4BhO2dW6wwlHQ2rajxIluZenAVjUVD+joeKN8MxBsGUnbYteTUL3lwP6DwIwGphGiodoAdjlDkXSYOoFqKP7Y46P0d/LFdL6C/1TE37Enk7YAAAAAElFTkSuQmCC>