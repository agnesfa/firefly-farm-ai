/**
 * Firefly Corner — Observation Code.gs Updates
 *
 * These are NEW handlers to ADD to the existing observation Code.gs deployment.
 * They add two new actions to the existing doPost and doGet handlers:
 *
 *   POST {action: "delete_imported", submission_id: "..."}
 *     — Deletes rows with matching submission_id WHERE status="imported"
 *     — Returns {success: true, deleted: N}
 *
 *   GET  ?action=get_media&submission_id=...
 *     — Fetches media files from Google Drive for a submission
 *     — Returns {success: true, files: [{filename, mime_type, data_base64}]}
 *
 * Integration instructions:
 *   1. Open the existing observation Code.gs
 *   2. In doPost(), add an "else if" for action === "delete_imported"
 *   3. In doGet(), add an "else if" for action === "get_media"
 *   4. Add the two handler functions below
 *   5. Deploy a new version
 */

// ── Add to doPost handler ──────────────────────────────────────
//
// In the existing doPost() function, add this case:
//
//   } else if (action === "delete_imported") {
//     return handleDeleteImported(body);
//   }

function handleDeleteImported(body) {
  var submissionId = body.submission_id;
  if (!submissionId) {
    return jsonResponse({ success: false, error: "Missing submission_id" });
  }

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Observations");
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, deleted: 0 });
  }

  var data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  // Find column indices (adjust based on actual sheet layout)
  // Assumes: submission_id is in a "Submission ID" column, status in a "Status" column
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var subIdCol = -1;
  var statusCol = -1;
  for (var c = 0; c < headers.length; c++) {
    var h = String(headers[c]).toLowerCase().replace(/\s+/g, "_");
    if (h === "submission_id" || h === "submissionid") subIdCol = c;
    if (h === "status") statusCol = c;
  }

  if (subIdCol === -1 || statusCol === -1) {
    return jsonResponse({
      success: false,
      error: "Could not find submission_id or status column in headers",
    });
  }

  // Collect row indices to delete (1-indexed, offset by header row)
  var rowsToDelete = [];
  for (var i = 0; i < data.length; i++) {
    if (
      String(data[i][subIdCol]) === submissionId &&
      String(data[i][statusCol]).toLowerCase() === "imported"
    ) {
      rowsToDelete.push(i + 2); // +2: 1-indexed + header row
    }
  }

  // Delete from bottom to top to avoid index shift
  rowsToDelete.sort(function (a, b) { return b - a; });
  for (var j = 0; j < rowsToDelete.length; j++) {
    sheet.deleteRow(rowsToDelete[j]);
  }

  return jsonResponse({ success: true, deleted: rowsToDelete.length });
}


// ── Add to doGet handler ───────────────────────────────────────
//
// In the existing doGet() function, add this case:
//
//   } else if (action === "get_media") {
//     return handleGetMedia(e.parameter);
//   }

function handleGetMedia(params) {
  var submissionId = params.submission_id;
  if (!submissionId) {
    return jsonResponse({ success: false, error: "Missing submission_id" });
  }

  // Find the submission in the Sheet to get date and section
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Observations");
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, files: [] });
  }

  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var subIdCol = -1;
  var dateCol = -1;
  var sectionCol = -1;
  for (var c = 0; c < headers.length; c++) {
    var h = String(headers[c]).toLowerCase().replace(/\s+/g, "_");
    if (h === "submission_id" || h === "submissionid") subIdCol = c;
    if (h === "date" || h === "timestamp") dateCol = c;
    if (h === "section" || h === "section_id") sectionCol = c;
  }

  if (subIdCol === -1) {
    return jsonResponse({ success: false, error: "Could not find submission_id column" });
  }

  // Find a matching row to get date and section
  var data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  var date = null;
  var section = null;
  for (var i = 0; i < data.length; i++) {
    if (String(data[i][subIdCol]) === submissionId) {
      if (dateCol !== -1) {
        var d = new Date(data[i][dateCol]);
        date = Utilities.formatDate(d, Session.getScriptTimeZone(), "yyyy-MM-dd");
      }
      if (sectionCol !== -1) {
        section = String(data[i][sectionCol]);
      }
      break;
    }
  }

  if (!date || !section) {
    return jsonResponse({ success: true, files: [], message: "No date/section found for submission" });
  }

  // Navigate Drive folder: {root}/{YYYY-MM-DD}/{section_id}/
  // Root folder ID — UPDATE THIS to match the actual Drive folder
  var ROOT_FOLDER_ID = "1_c1w_TLQMddsbDRg06er5_88c8hUCtgW"; // Firefly Corner AI Observations

  try {
    var rootFolder = DriveApp.getFolderById(ROOT_FOLDER_ID);
    var dateFolders = rootFolder.getFoldersByName(date);
    if (!dateFolders.hasNext()) {
      return jsonResponse({ success: true, files: [], message: "No folder for date: " + date });
    }

    var dateFolder = dateFolders.next();
    var sectionFolders = dateFolder.getFoldersByName(section);
    if (!sectionFolders.hasNext()) {
      return jsonResponse({ success: true, files: [], message: "No folder for section: " + section });
    }

    var sectionFolder = sectionFolders.next();
    var files = sectionFolder.getFiles();
    var results = [];

    while (files.hasNext()) {
      var file = files.next();
      var blob = file.getBlob();
      results.push({
        filename: file.getName(),
        mime_type: blob.getContentType(),
        data_base64: Utilities.base64Encode(blob.getBytes()),
      });
    }

    return jsonResponse({ success: true, files: results });
  } catch (err) {
    return jsonResponse({ success: false, error: "Drive error: " + err.message });
  }
}
