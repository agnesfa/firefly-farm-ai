/**
 * Firefly Corner — Team Memory Apps Script
 *
 * Deploy as a Google Apps Script Web App attached to the
 * "Firefly Corner - Team Memory" Google Sheet.
 *
 * Deployment settings:
 *   Execute as: Me (Agnes)
 *   Who has access: Anyone (for anonymous POST from MCP servers)
 *
 * Sheet columns (Row 1 headers):
 *   A: Timestamp
 *   B: User
 *   C: Topics
 *   D: Decisions
 *   E: FarmOS Changes
 *   F: Questions
 *   G: Summary
 *   H: Skip
 *   I: Acknowledged_By (JSON array of usernames, e.g. '["Agnes","Claire"]')
 *
 * Endpoints:
 *   GET  ?action=list[&days=7&user=...&limit=20&only_fresh_for=...]  — list recent summaries
 *   GET  ?action=search&query=...&days=30                           — search across text columns
 *   POST {action: "write_summary", user, topics, decisions, farmos_changes, questions, summary, skip}
 *   POST {action: "acknowledge", summary_id: <row_number>, user: "Claire"}
 */

// ── Configuration ──────────────────────────────────────────────

function getSheet() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Memory");
}

// ── GET handler ────────────────────────────────────────────────

function doGet(e) {
  try {
    var action = (e.parameter.action || "").toLowerCase();

    if (action === "list") {
      return handleList(e.parameter);
    } else if (action === "search") {
      return handleSearch(e.parameter);
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action });
    }
  } catch (err) {
    return jsonResponse({ success: false, error: err.message });
  }
}

// ── POST handler ───────────────────────────────────────────────

function doPost(e) {
  try {
    var body;
    if (e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    } else {
      return jsonResponse({ success: false, error: "No POST body" });
    }

    var action = (body.action || "").toLowerCase();

    if (action === "write_summary") {
      return handleWriteSummary(body);
    } else if (action === "acknowledge") {
      return handleAcknowledge(body);
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action });
    }
  } catch (err) {
    return jsonResponse({ success: false, error: err.message });
  }
}

// ── List recent summaries ──────────────────────────────────────

function handleList(params) {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, summaries: [], count: 0 });
  }

  var days = parseInt(params.days || "7", 10);
  var limit = parseInt(params.limit || "20", 10);
  var userFilter = (params.user || "").toLowerCase();

  var cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);

  var onlyFreshFor = (params.only_fresh_for || "").toLowerCase();

  var data = sheet.getRange(2, 1, lastRow - 1, 9).getValues();
  var results = [];

  // Iterate from newest to oldest (bottom to top)
  for (var i = data.length - 1; i >= 0; i--) {
    var row = data[i];
    var timestamp = new Date(row[0]);

    // Skip rows before cutoff
    if (timestamp < cutoff) continue;

    // Skip if user filter doesn't match
    if (userFilter && String(row[1]).toLowerCase() !== userFilter) continue;

    // Skip entries marked as "skip"
    if (String(row[7]).toLowerCase() === "true") continue;

    // Skip entries already acknowledged by this user (fresh-only filtering)
    if (onlyFreshFor) {
      var acknowledgedBy = parseAcknowledgedBy(row[8]);
      if (acknowledgedBy.indexOf(onlyFreshFor) !== -1) continue;
    }

    var rowNumber = i + 2; // 1-indexed, skip header
    results.push({
      summary_id: String(rowNumber),
      timestamp: timestamp.toISOString(),
      user: String(row[1]),
      topics: String(row[2]),
      decisions: String(row[3]),
      farmos_changes: String(row[4]),
      questions: String(row[5]),
      summary: String(row[6]),
    });

    if (results.length >= limit) break;
  }

  return jsonResponse({ success: true, summaries: results, count: results.length });
}

// ── Search across summaries ────────────────────────────────────

function handleSearch(params) {
  var query = (params.query || "").toLowerCase();
  if (!query) {
    return jsonResponse({ success: false, error: "Missing query parameter" });
  }

  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, results: [], count: 0 });
  }

  var days = parseInt(params.days || "30", 10);
  var cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);

  var data = sheet.getRange(2, 1, lastRow - 1, 9).getValues();
  var results = [];
  var maxResults = 20;

  // Search from newest to oldest
  for (var i = data.length - 1; i >= 0; i--) {
    var row = data[i];
    var timestamp = new Date(row[0]);

    if (timestamp < cutoff) continue;
    if (String(row[7]).toLowerCase() === "true") continue;

    // Search across Topics (C), Decisions (D), Questions (F), Summary (G)
    var searchable = [
      String(row[2]),  // Topics
      String(row[3]),  // Decisions
      String(row[5]),  // Questions
      String(row[6]),  // Summary
    ].join(" ").toLowerCase();

    if (searchable.indexOf(query) !== -1) {
      var rowNumber = i + 2;
      results.push({
        summary_id: String(rowNumber),
        timestamp: timestamp.toISOString(),
        user: String(row[1]),
        topics: String(row[2]),
        decisions: String(row[3]),
        farmos_changes: String(row[4]),
        questions: String(row[5]),
        summary: String(row[6]),
      });

      if (results.length >= maxResults) break;
    }
  }

  return jsonResponse({ success: true, results: results, count: results.length });
}

// ── Write a session summary ────────────────────────────────────

function handleWriteSummary(body) {
  var sheet = getSheet();

  var row = [
    new Date(),                           // A: Timestamp
    body.user || "Unknown",               // B: User
    body.topics || "",                     // C: Topics
    body.decisions || "",                  // D: Decisions
    body.farmos_changes || "",             // E: FarmOS Changes
    body.questions || "",                  // F: Questions
    body.summary || "",                    // G: Summary
    body.skip ? "true" : "false",         // H: Skip
    "",                                   // I: Acknowledged_By (empty initially)
  ];

  sheet.appendRow(row);

  return jsonResponse({
    success: true,
    message: "Summary saved for " + (body.user || "Unknown"),
  });
}

// ── Acknowledge a memory entry ────────────────────────────────

function handleAcknowledge(body) {
  var summaryId = body.summary_id;
  var user = (body.user || "").toLowerCase();

  if (!summaryId || !user) {
    return jsonResponse({ success: false, error: "Missing summary_id or user" });
  }

  var rowNum = parseInt(summaryId, 10);
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();

  if (isNaN(rowNum) || rowNum < 2 || rowNum > lastRow) {
    return jsonResponse({ success: false, error: "Invalid summary_id: " + summaryId });
  }

  // Read current acknowledged_by value (column I = 9)
  var cell = sheet.getRange(rowNum, 9);
  var current = parseAcknowledgedBy(cell.getValue());

  // Add user if not already acknowledged
  if (current.indexOf(user) === -1) {
    current.push(user);
    cell.setValue(JSON.stringify(current));
  }

  return jsonResponse({
    success: true,
    message: "Acknowledged by " + body.user,
    summary_id: summaryId,
    acknowledged_by: current,
  });
}

// ── Parse acknowledged_by JSON array ─────────────────────────

function parseAcknowledgedBy(value) {
  var str = String(value || "").trim();
  if (!str) return [];
  try {
    var arr = JSON.parse(str);
    if (Array.isArray(arr)) {
      return arr.map(function(u) { return String(u).toLowerCase(); });
    }
    return [];
  } catch (e) {
    return [];
  }
}

// ── Utility ────────────────────────────────────────────────────

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
