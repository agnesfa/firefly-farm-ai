/**
 * Firefly Corner — Plant Types Google Sheet Apps Script
 *
 * Deploy as a BOUND script on the "Firefly Corner - Plant Types"
 * Google Sheet (fireflyagents.com account).
 *
 * Deployment settings:
 *   Execute as: Me (Agnes)
 *   Who has access: Anyone (for anonymous POST from MCP servers)
 *
 * Sheet "Plant Types" columns (Row 1 headers — must match exactly):
 *   A: common_name
 *   B: variety
 *   C: farmos_name
 *   D: botanical_name
 *   E: crop_family
 *   F: origin
 *   G: description
 *   H: lifespan_years
 *   I: lifecycle_years
 *   J: maturity_days
 *   K: strata
 *   L: succession_stage
 *   M: plant_functions
 *   N: harvest_days
 *   O: germination_time
 *   P: transplant_days
 *   Q: source
 *
 * Endpoints:
 *   GET  ?action=health                    — health check + usage stats
 *   GET  ?action=list                     — list all plant types
 *   GET  ?action=search&query=...         — search by name (partial match)
 *   GET  ?action=reconcile                — compare sheet against farmOS-reported data
 *   POST {action: "add", ...fields}       — add a new plant type row
 *   POST {action: "update", farmos_name, ...fields} — update existing row by farmos_name
 *
 * Usage tracking:
 *   Requires UsageTracking.gs in the same project.
 */

// ── Configuration ──────────────────────────────────────────────

var SHEET_NAME = "Plant Types";

// Column mapping (0-indexed for array access)
var COLS = {
  common_name: 0,
  variety: 1,
  farmos_name: 2,
  botanical_name: 3,
  crop_family: 4,
  origin: 5,
  description: 6,
  lifespan_years: 7,
  lifecycle_years: 8,
  maturity_days: 9,
  strata: 10,
  succession_stage: 11,
  plant_functions: 12,
  harvest_days: 13,
  germination_time: 14,
  transplant_days: 15,
  source: 16
};

var COL_NAMES = [
  "common_name", "variety", "farmos_name", "botanical_name", "crop_family",
  "origin", "description", "lifespan_years", "lifecycle_years", "maturity_days",
  "strata", "succession_stage", "plant_functions", "harvest_days",
  "germination_time", "transplant_days", "source"
];

function getSheet() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
}

// ── GET handler ────────────────────────────────────────────────

function doGet(e) {
  try {
    trackExecution();
    var action = (e.parameter.action || "").toLowerCase();

    if (action === "health") {
      return handleHealth();
    } else if (action === "list") {
      return handleList(e.parameter);
    } else if (action === "search") {
      return handleSearch(e.parameter);
    } else if (action === "reconcile") {
      return handleReconcile(e.parameter);
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action + ". Use: health, list, search, reconcile" });
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
    } else if (action === "fix_formats") {
      return handleFixFormats(body);
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action + ". Use: add, update, fix_formats" });
    }
  } catch (err) {
    return jsonResponse({ success: false, error: err.message });
  }
}

// ── List all plant types ────────────────────────────────────────

function handleList(params) {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, plant_types: [], count: 0 });
  }

  var data = sheet.getRange(2, 1, lastRow - 1, COL_NAMES.length).getValues();
  var results = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var entry = {};
    for (var j = 0; j < COL_NAMES.length; j++) {
      entry[COL_NAMES[j]] = String(row[j] || "");
    }
    // Skip empty rows
    if (!entry.farmos_name && !entry.common_name) continue;
    results.push(entry);
  }

  return jsonResponse({ success: true, plant_types: results, count: results.length });
}

// ── Search by name ──────────────────────────────────────────────

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

  var data = sheet.getRange(2, 1, lastRow - 1, COL_NAMES.length).getValues();
  var results = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var farmosName = String(row[COLS.farmos_name] || "").toLowerCase();
    var commonName = String(row[COLS.common_name] || "").toLowerCase();
    var botanicalName = String(row[COLS.botanical_name] || "").toLowerCase();

    if (farmosName.indexOf(query) !== -1 ||
        commonName.indexOf(query) !== -1 ||
        botanicalName.indexOf(query) !== -1) {
      var entry = {};
      for (var j = 0; j < COL_NAMES.length; j++) {
        entry[COL_NAMES[j]] = String(row[j] || "");
      }
      results.push(entry);
    }
  }

  return jsonResponse({ success: true, results: results, count: results.length });
}

// ── Add a new plant type ────────────────────────────────────────

function handleAdd(body) {
  var sheet = getSheet();
  var farmosName = body.farmos_name || "";
  if (!farmosName) {
    return jsonResponse({ success: false, error: "Missing farmos_name" });
  }

  // Check for duplicates
  var lastRow = sheet.getLastRow();
  if (lastRow >= 2) {
    var existingNames = sheet.getRange(2, COLS.farmos_name + 1, lastRow - 1, 1).getValues();
    for (var i = 0; i < existingNames.length; i++) {
      if (String(existingNames[i][0]).toLowerCase() === farmosName.toLowerCase()) {
        return jsonResponse({
          success: false,
          error: "Plant type '" + farmosName + "' already exists in row " + (i + 2)
        });
      }
    }
  }

  // Build row from body fields
  var newRow = [];
  for (var j = 0; j < COL_NAMES.length; j++) {
    newRow.push(body[COL_NAMES[j]] || "");
  }

  sheet.appendRow(newRow);
  var newRowNum = sheet.getLastRow();

  // Force plain text format on numeric/range columns to prevent date auto-formatting
  var TEXT_COLS = [COLS.lifespan_years, COLS.lifecycle_years, COLS.maturity_days,
                   COLS.harvest_days, COLS.germination_time, COLS.transplant_days];
  for (var k = 0; k < TEXT_COLS.length; k++) {
    sheet.getRange(newRowNum, TEXT_COLS[k] + 1).setNumberFormat("@");
  }

  return jsonResponse({
    success: true,
    message: "Added plant type: " + farmosName,
    row: newRowNum
  });
}

// ── Update an existing plant type ───────────────────────────────

function handleUpdate(body) {
  var sheet = getSheet();
  var farmosName = body.farmos_name || "";
  if (!farmosName) {
    return jsonResponse({ success: false, error: "Missing farmos_name" });
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: false, error: "No data in sheet" });
  }

  // Find the row by farmos_name
  var data = sheet.getRange(2, 1, lastRow - 1, COL_NAMES.length).getValues();
  var targetRow = -1;

  for (var i = 0; i < data.length; i++) {
    if (String(data[i][COLS.farmos_name]).toLowerCase() === farmosName.toLowerCase()) {
      targetRow = i + 2; // +2 for 1-indexed + header row
      break;
    }
  }

  if (targetRow === -1) {
    return jsonResponse({
      success: false,
      error: "Plant type '" + farmosName + "' not found in sheet"
    });
  }

  // Fields that must be stored as plain text to prevent date auto-formatting
  var TEXT_FIELDS = ["lifespan_years", "lifecycle_years", "maturity_days",
                     "harvest_days", "germination_time", "transplant_days"];

  // Update only the fields that were provided (don't overwrite with empty)
  var updatedFields = [];
  for (var j = 0; j < COL_NAMES.length; j++) {
    var colName = COL_NAMES[j];
    if (colName === "farmos_name") continue; // Don't update the key field
    if (body.hasOwnProperty(colName) && body[colName] !== undefined && body[colName] !== null) {
      var cell = sheet.getRange(targetRow, j + 1);
      // Force plain text format for numeric/range fields that Sheets misinterprets as dates
      if (TEXT_FIELDS.indexOf(colName) !== -1) {
        cell.setNumberFormat("@");
      }
      cell.setValue(body[colName]);
      updatedFields.push(colName);
    }
  }

  if (updatedFields.length === 0) {
    return jsonResponse({
      success: true,
      message: "No fields to update for: " + farmosName,
      updated_fields: []
    });
  }

  return jsonResponse({
    success: true,
    message: "Updated plant type: " + farmosName,
    row: targetRow,
    updated_fields: updatedFields
  });
}

// ── Reconcile: compare sheet data for drift detection ───────────

function handleReconcile(params) {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, plant_types: [], count: 0 });
  }

  // Return all rows with key fields that can be compared against farmOS
  // The MCP client does the actual comparison — this just provides the sheet data
  var data = sheet.getRange(2, 1, lastRow - 1, COL_NAMES.length).getValues();
  var results = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var entry = {
      row_number: i + 2,
      farmos_name: String(row[COLS.farmos_name] || ""),
      strata: String(row[COLS.strata] || ""),
      succession_stage: String(row[COLS.succession_stage] || ""),
      botanical_name: String(row[COLS.botanical_name] || ""),
      crop_family: String(row[COLS.crop_family] || ""),
      plant_functions: String(row[COLS.plant_functions] || ""),
    };
    if (entry.farmos_name) {
      results.push(entry);
    }
  }

  return jsonResponse({ success: true, plant_types: results, count: results.length });
}

// ── Fix date-formatted columns ──────────────────────────────────

/**
 * Bulk-fix cell formats for lifespan_years (col H) and lifecycle_years (col I).
 * Sets the number format to plain text ("@") and rewrites each value as a string
 * to prevent Google Sheets from interpreting values like "3-10" as dates.
 *
 * Also accepts optional "values" dict mapping farmos_name → {lifespan_years, lifecycle_years}
 * to simultaneously fix format AND push correct values.
 *
 * POST {action: "fix_formats"}                    — fix format only (keeps current display values)
 * POST {action: "fix_formats", values: {...}}     — fix format AND push correct values
 */
function handleFixFormats(body) {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, message: "No data rows", fixed: 0 });
  }

  var numRows = lastRow - 1;
  var lifespanCol = COLS.lifespan_years + 1; // 1-indexed = 8
  var lifecycleCol = COLS.lifecycle_years + 1; // 1-indexed = 9

  // Set entire columns H and I to plain text format
  var lifespanRange = sheet.getRange(2, lifespanCol, numRows, 1);
  var lifecycleRange = sheet.getRange(2, lifecycleCol, numRows, 1);
  lifespanRange.setNumberFormat("@");
  lifecycleRange.setNumberFormat("@");

  // If values dict provided, push corrected values
  var valuesProvided = body.values || null;
  var fixed = 0;

  if (valuesProvided) {
    // Build lookup of farmos_name → row index
    var farmosNames = sheet.getRange(2, COLS.farmos_name + 1, numRows, 1).getValues();
    var nameToRow = {};
    for (var i = 0; i < farmosNames.length; i++) {
      nameToRow[String(farmosNames[i][0])] = i + 2; // 1-indexed + header
    }

    for (var name in valuesProvided) {
      var rowNum = nameToRow[name];
      if (!rowNum) continue;
      var vals = valuesProvided[name];
      if (vals.lifespan_years !== undefined) {
        sheet.getRange(rowNum, lifespanCol).setValue(String(vals.lifespan_years));
        fixed++;
      }
      if (vals.lifecycle_years !== undefined) {
        sheet.getRange(rowNum, lifecycleCol).setValue(String(vals.lifecycle_years));
        fixed++;
      }
    }
  } else {
    // No values provided — rewrite existing display values as strings
    // Read the DISPLAY values (getDisplayValues returns what users see, not internal dates)
    var lifespanDisplay = lifespanRange.getDisplayValues();
    var lifecycleDisplay = lifecycleRange.getDisplayValues();

    for (var r = 0; r < numRows; r++) {
      var lsVal = lifespanDisplay[r][0];
      var lcVal = lifecycleDisplay[r][0];
      if (lsVal) {
        sheet.getRange(r + 2, lifespanCol).setValue(lsVal);
        fixed++;
      }
      if (lcVal) {
        sheet.getRange(r + 2, lifecycleCol).setValue(lcVal);
        fixed++;
      }
    }
  }

  return jsonResponse({
    success: true,
    message: "Fixed format for lifespan_years and lifecycle_years columns to plain text",
    fixed: fixed
  });
}

// ── Utility ────────────────────────────────────────────────────

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
