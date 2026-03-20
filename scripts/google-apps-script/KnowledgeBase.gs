/**
 * Firefly Corner — Knowledge Base Google Sheet Apps Script
 *
 * Deploy as a BOUND script on the "Firefly Corner - Knowledge Base"
 * Google Sheet (fireflyagents.com account).
 *
 * Deployment settings:
 *   Execute as: Me (Agnes)
 *   Who has access: Anyone (for anonymous POST from MCP servers)
 *
 * Sheet "Knowledge" columns (Row 1 headers — must match exactly):
 *   A: entry_id       — Auto-generated UUID
 *   B: title          — Article/guide title
 *   C: category       — Content type: tutorial, sop, guide, reference, recipe, observation, source-material
 *   D: topics         — Farm domains (multi-value, comma-separated): nursery, compost, irrigation, syntropic, seeds, harvest, paddock, equipment, cooking, infrastructure, camp
 *   E: tags           — Free-form search keywords (species, techniques, tools)
 *   F: content        — Full text content
 *   G: author         — Who wrote this
 *   H: source_type    — tutorial, sop, guide, observation, recipe, reference
 *   I: media_links    — Comma-separated Drive file IDs or URLs
 *   J: related_plants — Comma-separated farmos_names
 *   K: related_sections — Comma-separated section IDs
 *   L: created        — ISO timestamp
 *   M: updated        — ISO timestamp (last update)
 *   N: status         — active or archived
 *
 * Endpoints:
 *   GET  ?action=health                                              — health check + usage stats
 *   GET  ?action=list[&category=...&topics=...&limit=...&offset=...]  — list entries
 *   GET  ?action=search&query=...[&category=...&topics=...]           — full-text search
 *   GET  ?action=categories                                — list distinct categories
 *   POST {action: "add", title, content, category, ...}    — add new entry
 *   POST {action: "update", entry_id, ...fields}           — update existing entry
 *   POST {action: "archive", entry_id}                     — soft-delete entry
 *
 * Usage tracking:
 *   Requires UsageTracking.gs in the same project.
 */

// ── Configuration ──────────────────────────────────────────────

var SHEET_NAME = "Knowledge";

var COLS = {
  entry_id: 0,
  title: 1,
  category: 2,
  topics: 3,
  tags: 4,
  content: 5,
  author: 6,
  source_type: 7,
  media_links: 8,
  related_plants: 9,
  related_sections: 10,
  created: 11,
  updated: 12,
  status: 13
};

var COL_NAMES = [
  "entry_id", "title", "category", "topics", "tags", "content", "author",
  "source_type", "media_links", "related_plants", "related_sections",
  "created", "updated", "status"
];

function getSheet() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
}

function generateId() {
  return Utilities.getUuid();
}

function nowISO() {
  return new Date().toISOString();
}

// ── GET handler ────────────────────────────────────────────────

function doGet(e) {
  try {
    var action = (e.parameter.action || "").toLowerCase();

    trackExecution();
    if (action === "health") {
      return handleHealth();
    } else if (action === "list") {
      return handleList(e.parameter);
    } else if (action === "search") {
      return handleSearch(e.parameter);
    } else if (action === "categories") {
      return handleCategories();
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action + ". Use: health, list, search, categories" });
    }
  } catch (err) {
    return jsonResponse({ success: false, error: err.message });
  }
}

// ── POST handler ───────────────────────────────────────────────

function doPost(e) {
  try {
    trackExecution();
    var body;
    if (e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    } else {
      return jsonResponse({ success: false, error: "No POST body" });
    }

    var action = (body.action || "").toLowerCase();

    if (action === "add") {
      return handleAdd(body);
    } else if (action === "update") {
      return handleUpdate(body);
    } else if (action === "archive") {
      return handleArchive(body);
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action + ". Use: add, update, archive" });
    }
  } catch (err) {
    return jsonResponse({ success: false, error: err.message });
  }
}

// ── List entries ───────────────────────────────────────────────

function handleList(params) {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, entries: [], count: 0, total: 0 });
  }

  var limit = parseInt(params.limit || "50", 10);
  var offset = parseInt(params.offset || "0", 10);
  var categoryFilter = (params.category || "").toLowerCase();

  var topicsFilter = (params.topics || "").toLowerCase();

  var data = sheet.getRange(2, 1, lastRow - 1, COL_NAMES.length).getValues();
  var filtered = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var status = String(row[COLS.status] || "active").toLowerCase();
    if (status === "archived") continue;

    if (categoryFilter) {
      var cat = String(row[COLS.category] || "").toLowerCase();
      if (cat !== categoryFilter) continue;
    }

    if (topicsFilter) {
      var rowTopics = String(row[COLS.topics] || "").toLowerCase();
      if (rowTopics.indexOf(topicsFilter) === -1) continue;
    }

    var entry = rowToEntry(row);
    if (entry.title || entry.content) {
      filtered.push(entry);
    }
  }

  // Sort by updated date descending (most recent first)
  filtered.sort(function(a, b) {
    return (b.updated || b.created || "").localeCompare(a.updated || a.created || "");
  });

  var total = filtered.length;
  var sliced = filtered.slice(offset, offset + limit);

  return jsonResponse({
    success: true,
    entries: sliced,
    count: sliced.length,
    total: total
  });
}

// ── Search ─────────────────────────────────────────────────────

function handleSearch(params) {
  var query = (params.query || "").toLowerCase();
  if (!query) {
    return jsonResponse({ success: false, error: "Missing query parameter" });
  }

  var categoryFilter = (params.category || "").toLowerCase();
  var topicsFilter = (params.topics || "").toLowerCase();

  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, results: [], count: 0 });
  }

  var data = sheet.getRange(2, 1, lastRow - 1, COL_NAMES.length).getValues();
  var results = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var status = String(row[COLS.status] || "active").toLowerCase();
    if (status === "archived") continue;

    if (categoryFilter) {
      var cat = String(row[COLS.category] || "").toLowerCase();
      if (cat !== categoryFilter) continue;
    }

    if (topicsFilter) {
      var rowTopics = String(row[COLS.topics] || "").toLowerCase();
      if (rowTopics.indexOf(topicsFilter) === -1) continue;
    }

    // Search across title, content, topics, tags, related_plants, author, category
    var searchable = [
      String(row[COLS.title] || ""),
      String(row[COLS.content] || ""),
      String(row[COLS.topics] || ""),
      String(row[COLS.tags] || ""),
      String(row[COLS.related_plants] || ""),
      String(row[COLS.author] || ""),
      String(row[COLS.category] || ""),
    ].join(" ").toLowerCase();

    if (searchable.indexOf(query) !== -1) {
      results.push(rowToEntry(row));
    }
  }

  // Sort by relevance (title match first, then by recency)
  results.sort(function(a, b) {
    var aTitle = (a.title || "").toLowerCase().indexOf(query) !== -1 ? 1 : 0;
    var bTitle = (b.title || "").toLowerCase().indexOf(query) !== -1 ? 1 : 0;
    if (aTitle !== bTitle) return bTitle - aTitle;
    return (b.updated || b.created || "").localeCompare(a.updated || a.created || "");
  });

  return jsonResponse({ success: true, results: results, count: results.length });
}

// ── Categories ─────────────────────────────────────────────────

function handleCategories() {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, categories: [] });
  }

  var catData = sheet.getRange(2, COLS.category + 1, lastRow - 1, 1).getValues();
  var statusData = sheet.getRange(2, COLS.status + 1, lastRow - 1, 1).getValues();
  var cats = {};

  for (var i = 0; i < catData.length; i++) {
    var status = String(statusData[i][0] || "active").toLowerCase();
    if (status === "archived") continue;

    var cat = String(catData[i][0] || "").trim();
    if (cat) {
      cats[cat] = (cats[cat] || 0) + 1;
    }
  }

  var result = [];
  for (var c in cats) {
    result.push({ name: c, count: cats[c] });
  }
  result.sort(function(a, b) { return b.count - a.count; });

  return jsonResponse({ success: true, categories: result });
}

// ── Add entry ──────────────────────────────────────────────────

function handleAdd(body) {
  var sheet = getSheet();
  var title = body.title || "";
  var content = body.content || "";
  var category = body.category || "general";

  if (!title) {
    return jsonResponse({ success: false, error: "Missing title" });
  }
  if (!content) {
    return jsonResponse({ success: false, error: "Missing content" });
  }

  var entryId = generateId();
  var now = nowISO();

  var newRow = [];
  for (var j = 0; j < COL_NAMES.length; j++) {
    var col = COL_NAMES[j];
    if (col === "entry_id") {
      newRow.push(entryId);
    } else if (col === "created") {
      newRow.push(now);
    } else if (col === "updated") {
      newRow.push(now);
    } else if (col === "status") {
      newRow.push("active");
    } else if (col === "category") {
      newRow.push(category);
    } else {
      newRow.push(body[col] || "");
    }
  }

  sheet.appendRow(newRow);

  return jsonResponse({
    success: true,
    message: "Added knowledge entry: " + title,
    entry_id: entryId,
    row: sheet.getLastRow()
  });
}

// ── Update entry ───────────────────────────────────────────────

function handleUpdate(body) {
  var sheet = getSheet();
  var entryId = body.entry_id || "";
  if (!entryId) {
    return jsonResponse({ success: false, error: "Missing entry_id" });
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: false, error: "No data in sheet" });
  }

  // Find row by entry_id
  var ids = sheet.getRange(2, COLS.entry_id + 1, lastRow - 1, 1).getValues();
  var targetRow = -1;
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === entryId) {
      targetRow = i + 2;
      break;
    }
  }

  if (targetRow === -1) {
    return jsonResponse({ success: false, error: "Entry not found: " + entryId });
  }

  // Updatable fields (not entry_id, created, status)
  var updatable = ["title", "category", "topics", "tags", "content", "author",
                    "source_type", "media_links", "related_plants", "related_sections"];
  var updatedFields = [];

  for (var k = 0; k < updatable.length; k++) {
    var field = updatable[k];
    if (body.hasOwnProperty(field) && body[field] !== undefined && body[field] !== null) {
      var colIdx = COLS[field] + 1; // 1-indexed
      sheet.getRange(targetRow, colIdx).setValue(body[field]);
      updatedFields.push(field);
    }
  }

  // Always update the "updated" timestamp
  sheet.getRange(targetRow, COLS.updated + 1).setValue(nowISO());

  return jsonResponse({
    success: true,
    message: "Updated entry: " + entryId,
    entry_id: entryId,
    updated_fields: updatedFields
  });
}

// ── Archive entry ──────────────────────────────────────────────

function handleArchive(body) {
  var sheet = getSheet();
  var entryId = body.entry_id || "";
  if (!entryId) {
    return jsonResponse({ success: false, error: "Missing entry_id" });
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: false, error: "No data in sheet" });
  }

  var ids = sheet.getRange(2, COLS.entry_id + 1, lastRow - 1, 1).getValues();
  var targetRow = -1;
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === entryId) {
      targetRow = i + 2;
      break;
    }
  }

  if (targetRow === -1) {
    return jsonResponse({ success: false, error: "Entry not found: " + entryId });
  }

  sheet.getRange(targetRow, COLS.status + 1).setValue("archived");
  sheet.getRange(targetRow, COLS.updated + 1).setValue(nowISO());

  // Optionally append reason to content
  var reason = body.reason || "";
  if (reason) {
    var currentContent = sheet.getRange(targetRow, COLS.content + 1).getValue();
    sheet.getRange(targetRow, COLS.content + 1).setValue(
      currentContent + "\n\n[Archived " + nowISO() + ": " + reason + "]"
    );
  }

  return jsonResponse({
    success: true,
    message: "Archived entry: " + entryId
  });
}

// ── Utility ────────────────────────────────────────────────────

function rowToEntry(row) {
  var entry = {};
  for (var j = 0; j < COL_NAMES.length; j++) {
    entry[COL_NAMES[j]] = String(row[j] || "");
  }
  return entry;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
