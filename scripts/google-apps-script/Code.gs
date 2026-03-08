/**
 * Firefly Corner Farm — Field Observation Backend
 *
 * Google Apps Script web app that receives field observations from
 * QR code landing pages and saves them to Google Sheets + Drive.
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
const SHEET_ID = "1wLAIxcSE_DNWjZdhlmPtQacvxg1VxHkA70hvX6nGqRs";

/** ID of the "Firefly Corner AI Observations" Google Drive folder */
const DRIVE_FOLDER_ID = "1WE1eMNEn--xW6RT7lAGnh0MFfJh4WCPX";

/** Sheet tab name for observation data */
const SHEET_NAME = "Observations";

// ─── WEB APP HANDLERS ───────────────────────────────────────

/**
 * Handle POST requests from observe pages.
 * Receives JSON observation data, saves to Sheet + Drive.
 */
function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents);

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

    // Save media files to Drive (Phase B)
    var mediaFiles = [];
    if (payload.media && payload.media.length > 0) {
      mediaFiles = saveMediaToDrive(payload);
    }

    return jsonResponse({
      success: true,
      message: rowCount + " observation(s) recorded",
      media_saved: mediaFiles.length
    });

  } catch (err) {
    return jsonResponse({ success: false, error: err.toString() });
  }
}

/**
 * Handle GET requests — health check endpoint.
 */
function doGet(e) {
  return jsonResponse({
    status: "ok",
    version: "1",
    service: "Firefly Corner Field Observations"
  });
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
    sheet.appendRow([
      "Submission ID", "Timestamp", "Section ID", "Observer",
      "Mode", "Species", "Strata", "Previous Count", "New Count",
      "Condition", "Plant Notes", "Section Notes",
      "Media Files", "Reviewed", "Imported to farmOS"
    ]);
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
      false,
      false
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
        false,
        false
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
    if (data[i][0] === submissionId) return true;
  }
  return false;
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
