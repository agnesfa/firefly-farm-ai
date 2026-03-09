/**
 * Firefly Corner Farm — Field Observation Backend (v2)
 *
 * Google Apps Script web app that receives field observations from
 * QR code landing pages, supports review workflows, and saves to
 * Google Sheets + Drive.
 *
 * Endpoints:
 *   GET  ?action=list[&status=pending&section=P2R3.14-21&observer=Claire]
 *        → Returns observations as JSON array
 *   GET  ?action=health
 *        → Health check (default if no action specified)
 *   POST {observation payload}
 *        → Save new field observation (from observe pages)
 *   POST {action: "update_status", rows: [{row_id, status, reviewer, notes}]}
 *        → Update review status of observation rows
 *
 * Status workflow: pending → reviewed → approved → imported
 *   - pending:  New observation from the field
 *   - reviewed: Claire has verified accuracy
 *   - approved: Agnes has approved for farmOS import
 *   - imported: Data has been pushed to farmOS
 *   - rejected: Observation was incorrect, will not be imported
 *
 * Deployment:
 *   1. Create a new Google Apps Script project at script.google.com
 *   2. Paste this code into Code.gs
 *   3. Deploy → New deployment → Web app
 *      - Execute as: Me (your account)
 *      - Who has access: Anyone
 *   4. Copy the deployment URL → use as OBSERVE_ENDPOINT
 *
 * The deployed URL looks like:
 *   https://script.google.com/macros/s/AKfycb.../exec
 */

// ─── CONFIGURATION ──────────────────────────────────────────

/** ID of the "Firefly Corner - Field Observations" Google Sheet */
const SHEET_ID = "11EUdwJkvvYZ8wXZSYYeudmLHO6dOs2iUIL4uZC-Gf8Q";

/** ID of the "Firefly Corner AI Observations" Google Drive folder */
const DRIVE_FOLDER_ID = "1_c1w_TLQMddsbDRg06er5_88c8hUCtgW";

/** Sheet tab name for observation data */
const SHEET_NAME = "Observations";

/** Column indices (0-based) — must match HEADERS array */
const COL = {
  SUBMISSION_ID: 0,
  TIMESTAMP: 1,
  SECTION_ID: 2,
  OBSERVER: 3,
  MODE: 4,
  SPECIES: 5,
  STRATA: 6,
  PREVIOUS_COUNT: 7,
  NEW_COUNT: 8,
  CONDITION: 9,
  PLANT_NOTES: 10,
  SECTION_NOTES: 11,
  MEDIA_FILES: 12,
  STATUS: 13,
  REVIEWER: 14,
  REVIEWER_NOTES: 15
};

/** Sheet headers — v2 adds Status/Reviewer/Reviewer Notes (replaces Reviewed/Imported booleans) */
const HEADERS = [
  "Submission ID", "Timestamp", "Section ID", "Observer",
  "Mode", "Species", "Strata", "Previous Count", "New Count",
  "Condition", "Plant Notes", "Section Notes",
  "Media Files", "Status", "Reviewer", "Reviewer Notes"
];

// ─── WEB APP HANDLERS ───────────────────────────────────────

/**
 * Handle POST requests.
 * Two actions:
 *   1. Field observation submission (default) — from observe pages
 *   2. Status update — from review workflow (action: "update_status")
 */
function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents);

    // Route based on action
    if (payload.action === "update_status") {
      return handleUpdateStatus(payload);
    }

    // Default: field observation submission
    return handleObservation(payload);

  } catch (err) {
    return jsonResponse({ success: false, error: err.toString() });
  }
}

/**
 * Handle GET requests.
 * Actions: list (return observations), health (default).
 */
function doGet(e) {
  var params = e ? (e.parameter || {}) : {};
  var action = params.action || "health";

  if (action === "list") {
    return handleListObservations(params);
  }

  // Default: health check
  return jsonResponse({
    status: "ok",
    version: "2",
    service: "Firefly Corner Field Observations"
  });
}

// ─── OBSERVATION SUBMISSION ──────────────────────────────────

/**
 * Handle a new field observation submission.
 */
function handleObservation(payload) {
  // Validate required fields
  if (!payload.section_id || !payload.observer || !payload.timestamp) {
    return jsonResponse({ success: false, error: "Missing required fields" });
  }

  // Check for duplicate submission
  if (payload.submission_id && isDuplicate(payload.submission_id)) {
    return jsonResponse({ success: true, message: "Already received", duplicate: true });
  }

  // Save structured data to Google Sheet
  var rowCount = appendToSheet(payload);

  // Save raw JSON to Drive folder
  saveJsonToDrive(payload);

  // Save media files to Drive
  var mediaFiles = [];
  if (payload.media && payload.media.length > 0) {
    mediaFiles = saveMediaToDrive(payload);
  }

  return jsonResponse({
    success: true,
    message: rowCount + " observation(s) recorded",
    media_saved: mediaFiles.length
  });
}

// ─── LIST OBSERVATIONS ───────────────────────────────────────

/**
 * Return observations as JSON array with optional filters.
 *
 * Query params:
 *   status   — filter by status (pending, reviewed, approved, imported, rejected)
 *   section  — filter by section ID (exact match)
 *   observer — filter by observer name (case-insensitive)
 *   date     — filter by date (YYYY-MM-DD, matches start of timestamp)
 *   submission_id — filter by submission ID (exact match)
 */
function handleListObservations(params) {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
  if (!sheet) {
    return jsonResponse({ success: true, observations: [], count: 0 });
  }

  var data = sheet.getDataRange().getValues();
  if (data.length <= 1) {
    return jsonResponse({ success: true, observations: [], count: 0 });
  }

  var observations = [];

  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    var rowNum = i + 1; // 1-based row number in Sheet

    // Build observation object
    var obs = {
      row_id: rowNum,
      submission_id: row[COL.SUBMISSION_ID] || "",
      timestamp: row[COL.TIMESTAMP] || "",
      section_id: row[COL.SECTION_ID] || "",
      observer: row[COL.OBSERVER] || "",
      mode: row[COL.MODE] || "",
      species: row[COL.SPECIES] || "",
      strata: row[COL.STRATA] || "",
      previous_count: row[COL.PREVIOUS_COUNT],
      new_count: row[COL.NEW_COUNT],
      condition: row[COL.CONDITION] || "",
      plant_notes: row[COL.PLANT_NOTES] || "",
      section_notes: row[COL.SECTION_NOTES] || "",
      media_files: row[COL.MEDIA_FILES] || "",
      status: normalizeStatus(row[COL.STATUS]),
      reviewer: row[COL.REVIEWER] || "",
      reviewer_notes: row[COL.REVIEWER_NOTES] || ""
    };

    // Handle Timestamp as Date object (Sheets may return Date)
    if (obs.timestamp instanceof Date) {
      obs.timestamp = obs.timestamp.toISOString();
    }

    // Apply filters
    if (params.status && obs.status !== params.status) continue;
    if (params.section && obs.section_id !== params.section) continue;
    if (params.observer && obs.observer.toLowerCase() !== params.observer.toLowerCase()) continue;
    if (params.date && obs.timestamp.substring(0, 10) !== params.date) continue;
    if (params.submission_id && obs.submission_id !== params.submission_id) continue;

    observations.push(obs);
  }

  return jsonResponse({
    success: true,
    observations: observations,
    count: observations.length
  });
}

/**
 * Normalize status values from the Sheet.
 * Handles legacy boolean values from v1 and missing values.
 */
function normalizeStatus(value) {
  if (value === "" || value === null || value === undefined) return "pending";
  if (value === false || value === "FALSE" || value === "false") return "pending";
  if (value === true || value === "TRUE" || value === "true") return "reviewed";
  var s = String(value).toLowerCase().trim();
  if (["pending", "reviewed", "approved", "imported", "rejected"].indexOf(s) >= 0) return s;
  return "pending";
}

// ─── STATUS UPDATE ───────────────────────────────────────────

/**
 * Update the status of observation rows.
 *
 * Payload format:
 * {
 *   action: "update_status",
 *   updates: [
 *     { row_id: 5, status: "reviewed", reviewer: "Claire", notes: "Confirmed 3 pigeon peas" },
 *     { row_id: 6, status: "rejected", reviewer: "Claire", notes: "Wrong species — was Tagasaste not Pigeon Pea" }
 *   ]
 * }
 *
 * Or update by submission_id (updates ALL rows with that submission_id):
 * {
 *   action: "update_status",
 *   updates: [
 *     { submission_id: "abc-123", status: "reviewed", reviewer: "Claire", notes: "All correct" }
 *   ]
 * }
 */
function handleUpdateStatus(payload) {
  var updates = payload.updates || [];
  if (updates.length === 0) {
    return jsonResponse({ success: false, error: "No updates provided" });
  }

  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
  if (!sheet) {
    return jsonResponse({ success: false, error: "Sheet not found" });
  }

  var data = sheet.getDataRange().getValues();
  var updated = 0;
  var errors = [];

  for (var u = 0; u < updates.length; u++) {
    var upd = updates[u];
    var status = upd.status;
    var reviewer = upd.reviewer || "";
    var notes = upd.notes || "";

    // Validate status value
    if (["pending", "reviewed", "approved", "imported", "rejected"].indexOf(status) < 0) {
      errors.push("Invalid status: " + status);
      continue;
    }

    if (upd.row_id) {
      // Update by row_id (1-based row number)
      var rowIdx = upd.row_id;
      if (rowIdx < 2 || rowIdx > data.length) {
        errors.push("Row " + rowIdx + " out of range");
        continue;
      }
      sheet.getRange(rowIdx, COL.STATUS + 1).setValue(status);
      sheet.getRange(rowIdx, COL.REVIEWER + 1).setValue(reviewer);
      sheet.getRange(rowIdx, COL.REVIEWER_NOTES + 1).setValue(notes);
      updated++;

    } else if (upd.submission_id) {
      // Update all rows with matching submission_id
      for (var i = 1; i < data.length; i++) {
        if (data[i][COL.SUBMISSION_ID] === upd.submission_id) {
          var rowNum = i + 1;
          sheet.getRange(rowNum, COL.STATUS + 1).setValue(status);
          sheet.getRange(rowNum, COL.REVIEWER + 1).setValue(reviewer);
          sheet.getRange(rowNum, COL.REVIEWER_NOTES + 1).setValue(notes);
          updated++;
        }
      }
    } else {
      errors.push("Update must have row_id or submission_id");
    }
  }

  var result = { success: true, updated: updated };
  if (errors.length > 0) result.errors = errors;
  return jsonResponse(result);
}

// ─── SHEET OPERATIONS ────────────────────────────────────────

/**
 * Append observation rows to the Google Sheet.
 * Creates one row per observed plant species.
 */
function appendToSheet(payload) {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);

  // Create sheet with headers if it doesn't exist
  if (!sheet) {
    sheet = SpreadsheetApp.openById(SHEET_ID).insertSheet(SHEET_NAME);
    sheet.appendRow(HEADERS);
    sheet.getRange("1:1").setFontWeight("bold");
    sheet.setFrozenRows(1);
  }

  var observations = payload.observations || [];
  var rowCount = 0;

  if (observations.length === 0) {
    // Section-only observation (notes/photos, no plant data)
    sheet.appendRow([
      payload.submission_id || "",
      payload.timestamp,
      payload.section_id,
      payload.observer,
      payload.mode || "quick",
      "", // species
      "", // strata
      "", // previous_count
      "", // new_count
      "", // condition
      "", // plant notes
      payload.section_notes || "",
      mediaFilesList(payload.media),
      "pending",
      "", // reviewer
      ""  // reviewer notes
    ]);
    rowCount = 1;
  } else {
    for (var i = 0; i < observations.length; i++) {
      var obs = observations[i];
      sheet.appendRow([
        payload.submission_id || "",
        payload.timestamp,
        payload.section_id,
        payload.observer,
        payload.mode || "quick",
        obs.species || "",
        obs.strata || "",
        obs.previous_count != null ? obs.previous_count : "",
        obs.new_count != null ? obs.new_count : "",
        obs.condition || "alive",
        obs.notes || "",
        payload.section_notes || "",
        mediaFilesList(payload.media),
        "pending",
        "", // reviewer
        ""  // reviewer notes
      ]);
      rowCount++;
    }
  }

  return rowCount;
}

/**
 * Check if a submission_id already exists in the sheet.
 */
function isDuplicate(submissionId) {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
  if (!sheet) return false;

  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (data[i][COL.SUBMISSION_ID] === submissionId) return true;
  }
  return false;
}

// ─── MIGRATE V1 HEADERS ─────────────────────────────────────

/**
 * One-time migration: update v1 headers to v2.
 * Run manually from Apps Script editor after deploying v2 Code.gs.
 *
 * Changes:
 *   Col N: "Reviewed" (boolean) → "Status" (string: pending/reviewed/approved/imported/rejected)
 *   Col O: "Imported to farmOS" (boolean) → "Reviewer" (string)
 *   Col P: (new) → "Reviewer Notes" (string)
 *
 * Also converts existing boolean values:
 *   Reviewed=false → Status="pending"
 *   Reviewed=true  → Status="reviewed"
 */
function migrateV1ToV2() {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
  if (!sheet) {
    Logger.log("No Observations sheet found");
    return;
  }

  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();

  // Check if already migrated (header says "Status")
  var currentHeader = sheet.getRange(1, COL.STATUS + 1).getValue();
  if (currentHeader === "Status") {
    Logger.log("Already migrated to v2");
    return;
  }

  // Update headers
  sheet.getRange(1, COL.STATUS + 1).setValue("Status");
  sheet.getRange(1, COL.REVIEWER + 1).setValue("Reviewer");

  // Add Reviewer Notes column if needed
  if (lastCol < HEADERS.length) {
    sheet.getRange(1, COL.REVIEWER_NOTES + 1).setValue("Reviewer Notes");
  }

  // Convert existing data rows
  if (lastRow > 1) {
    for (var i = 2; i <= lastRow; i++) {
      var reviewed = sheet.getRange(i, COL.STATUS + 1).getValue();
      var imported = sheet.getRange(i, COL.REVIEWER + 1).getValue();

      // Convert boolean Reviewed to Status string
      var status = "pending";
      if (imported === true || imported === "TRUE") {
        status = "imported";
      } else if (reviewed === true || reviewed === "TRUE") {
        status = "reviewed";
      }

      sheet.getRange(i, COL.STATUS + 1).setValue(status);
      sheet.getRange(i, COL.REVIEWER + 1).setValue(""); // Clear old "Imported to farmOS" value
      sheet.getRange(i, COL.REVIEWER_NOTES + 1).setValue(""); // New empty column
    }
  }

  Logger.log("Migration complete: " + (lastRow - 1) + " rows updated");
}

// ─── DRIVE OPERATIONS ────────────────────────────────────────

/**
 * Save the raw JSON payload to Google Drive.
 * Folder structure: {root}/{date}/{section_id}/
 */
function saveJsonToDrive(payload) {
  var folder = getObservationFolder(payload);
  var timestamp = payload.timestamp.replace(/[:.]/g, "").replace("T", "_").substring(0, 15);
  var filename = "observation_" + timestamp + ".json";

  // Strip media data from the JSON copy (too large, saved separately)
  var jsonCopy = JSON.parse(JSON.stringify(payload));
  if (jsonCopy.media) {
    for (var i = 0; i < jsonCopy.media.length; i++) {
      jsonCopy.media[i].data = "[saved to Drive]";
    }
  }

  folder.createFile(filename, JSON.stringify(jsonCopy, null, 2), "application/json");
}

/**
 * Save media files (photos, audio) to Google Drive.
 * Returns array of saved filenames.
 */
function saveMediaToDrive(payload) {
  var folder = getObservationFolder(payload);
  var savedFiles = [];

  for (var i = 0; i < payload.media.length; i++) {
    var media = payload.media[i];
    if (!media.data) continue;

    try {
      // Extract base64 data (strip "data:image/jpeg;base64," prefix)
      var parts = media.data.split(",");
      var base64Data = parts.length > 1 ? parts[1] : parts[0];
      var mimeType = media.type === "audio" ? "audio/webm" : "image/jpeg";

      if (parts.length > 1 && parts[0].indexOf(":") > -1) {
        mimeType = parts[0].split(":")[1].split(";")[0];
      }

      var decoded = Utilities.base64Decode(base64Data);
      var blob = Utilities.newBlob(decoded, mimeType, media.filename || ("media_" + (i + 1)));
      folder.createFile(blob);
      savedFiles.push(media.filename || ("media_" + (i + 1)));
    } catch (err) {
      Logger.log("Failed to save media file " + i + ": " + err);
    }
  }

  return savedFiles;
}

/**
 * Get or create the observation folder for a given payload.
 * Structure: {root}/{YYYY-MM-DD}/{section_id}/
 */
function getObservationFolder(payload) {
  var root = DriveApp.getFolderById(DRIVE_FOLDER_ID);

  // Date folder (YYYY-MM-DD)
  var date = payload.timestamp.substring(0, 10);
  var dateFolder = getOrCreateSubfolder(root, date);

  // Section folder
  var sectionFolder = getOrCreateSubfolder(dateFolder, payload.section_id);

  return sectionFolder;
}

/**
 * Get an existing subfolder or create it.
 */
function getOrCreateSubfolder(parent, name) {
  var folders = parent.getFoldersByName(name);
  if (folders.hasNext()) {
    return folders.next();
  }
  return parent.createFolder(name);
}

// ─── HELPERS ─────────────────────────────────────────────────

/**
 * Create a JSON response with proper content type.
 */
function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Extract comma-separated list of media filenames.
 */
function mediaFilesList(media) {
  if (!media || media.length === 0) return "";
  return media.map(function(m) { return m.filename || "unnamed"; }).join(", ");
}
