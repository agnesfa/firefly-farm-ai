/**
 * Firefly Corner — Seed Bank Apps Script
 *
 * Deploy as a BOUND script on the "Firefly Corner - Seed Bank Inventory"
 * Google Sheet (fireflyagents.com account).
 *
 * Deployment settings:
 *   Execute as: Me (Agnes)
 *   Who has access: Anyone (for anonymous POST from QR pages)
 *
 * Usage tracking:
 *   Requires UsageTracking.gs in the same project.
 *
 * Sheet tabs:
 *   "Inventory" — seed stock data (row 1 headers, row 2+ data)
 *     Columns A-Q (plant type enrichment from plant_types.csv):
 *       A (0):  common_name
 *       B (1):  variety
 *       C (2):  farmos_name       — primary lookup key (matches farmOS plant_type)
 *       D (3):  botanical_name
 *       E (4):  crop_family
 *       F (5):  origin
 *       G (6):  description
 *       H (7):  lifespan_years
 *       I (8):  lifecycle_years
 *       J (9):  maturity_days
 *       K (10): strata
 *       L (11): succession_stage
 *       M (12): plant_functions
 *       N (13): harvest_days
 *       O (14): germination_time
 *       P (15): transplant_days
 *       Q (16): source
 *     Columns R-AA (seed bank specific from seed_bank.csv):
 *       R (17): quantity_grams    — weight in grams (for bulk seeds)
 *       S (18): stock_level       — 0 / 0.5 / 1 (for sachets: Empty/Half/Full)
 *       T (19): unit              — "sachet" or "bulk"
 *       U (20): expiry_date       — packet expiry (e.g. "Jun-26")
 *       V (21): quality           — G=good, B=bad
 *       W (22): inventory_date    — last manual count date
 *       X (23): dominant_function — edible, companion, biomass, etc.
 *       Y (24): season_to_plant   — spring-summer, autumn-winter, etc.
 *       Z (25): qty_seeds_per_m2  — sowing density
 *       AA(26): data_source
 *     Columns AB-AD (added for QR page workflow):
 *       AB(27): location          — "Fridge" or "Freezer" (default: Fridge)
 *       AC(28): replenish_flag    — TRUE/FALSE
 *       AD(29): last_updated      — auto-set timestamp on each transaction
 *
 *   "Transactions" — audit log of all seed transactions (auto-created)
 *       A: Timestamp
 *       B: User
 *       C: Seed (farmos_name)
 *       D: Type (take / add / status_change)
 *       E: Grams (amount taken or added, for bulk)
 *       F: New Stock Level (for sachets: 0, 0.5, 1)
 *       G: Previous Value (what it was before)
 *       H: Replenish Flag (TRUE/FALSE)
 *       I: Notes
 *
 * Endpoints:
 *   GET  ?action=health                    — health check + usage stats
 *   GET  ?action=search&query=basil        — search seeds by name
 *   GET  ?action=inventory[&replenish=true] — full inventory or just flagged items
 *   POST {action: "transaction", ...}      — record a seed transaction
 */

// ── Configuration ──────────────────────────────────────────────

var INV_TAB = "Inventory";
var TXN_TAB = "Transactions";
var INV_COLS = 30; // A through AD

// Inventory column indices (0-based) — matches Claire's 30-column Google Sheet layout
var INV = {
  // Plant type enrichment (A-Q, cols 0-16)
  COMMON_NAME: 0,       // A
  VARIETY: 1,            // B
  FARMOS_NAME: 2,        // C — primary lookup key
  BOTANICAL_NAME: 3,     // D
  CROP_FAMILY: 4,        // E
  ORIGIN: 5,             // F
  DESCRIPTION: 6,        // G
  LIFESPAN_YEARS: 7,     // H
  LIFECYCLE_YEARS: 8,    // I
  MATURITY_DAYS: 9,      // J
  STRATA: 10,            // K
  SUCCESSION_STAGE: 11,  // L
  PLANT_FUNCTIONS: 12,   // M
  HARVEST_DAYS: 13,      // N
  GERMINATION_TIME: 14,  // O
  TRANSPLANT_DAYS: 15,   // P
  SOURCE: 16,            // Q
  // Seed bank specific (R-AA, cols 17-26)
  QTY_GRAMS: 17,         // R
  STOCK_LEVEL: 18,       // S
  UNIT: 19,              // T
  EXPIRY: 20,            // U
  QUALITY: 21,           // V
  INVENTORY_DATE: 22,    // W
  FUNCTION: 23,          // X — dominant_function
  SEASON: 24,            // Y — season_to_plant
  SEEDS_PER_M2: 25,      // Z
  DATA_SOURCE: 26,       // AA
  // QR page workflow (AB-AD, cols 27-29)
  LOCATION: 27,          // AB
  REPLENISH: 28,         // AC
  LAST_UPDATED: 29       // AD
};

// ── GET handler ────────────────────────────────────────────────

function doGet(e) {
  try {
    trackExecution();
    var action = (e.parameter.action || "").toLowerCase();

    if (action === "health") {
      return handleHealth();
    } else if (action === "search") {
      return handleSearch(e.parameter);
    } else if (action === "inventory") {
      return handleInventory(e.parameter);
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action + ". Use: health, search, inventory" });
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

    if (action === "transaction") {
      return handleTransaction(body);
    } else {
      return jsonResponse({ success: false, error: "Unknown action: " + action + ". Use: transaction" });
    }
  } catch (err) {
    return jsonResponse({ success: false, error: err.message });
  }
}

// ── Search seeds ───────────────────────────────────────────────

function handleSearch(params) {
  var query = (params.query || "").toLowerCase().trim();
  if (!query) {
    return jsonResponse({ success: false, error: "Missing query parameter" });
  }

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(INV_TAB);
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, seeds: [], count: 0 });
  }

  var data = sheet.getRange(2, 1, lastRow - 1, INV_COLS).getValues();
  trackCellReads((lastRow - 1) * INV_COLS);
  var results = [];
  var maxResults = 30;

  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var commonName = String(row[INV.COMMON_NAME]).toLowerCase();
    var variety = String(row[INV.VARIETY]).toLowerCase();
    var farmosName = String(row[INV.FARMOS_NAME]).toLowerCase();
    var botanicalName = String(row[INV.BOTANICAL_NAME]).toLowerCase();

    // Match against name fields: common_name, variety, farmos_name, botanical_name
    if (commonName.indexOf(query) !== -1 ||
        variety.indexOf(query) !== -1 ||
        farmosName.indexOf(query) !== -1 ||
        botanicalName.indexOf(query) !== -1) {

      results.push(buildSeedResult(row, i + 2));
      if (results.length >= maxResults) break;
    }
  }

  return jsonResponse({ success: true, seeds: results, count: results.length });
}

// ── Full inventory ─────────────────────────────────────────────

function handleInventory(params) {
  var replenishOnly = (params.replenish || "").toLowerCase() === "true";

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(INV_TAB);
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: true, seeds: [], count: 0 });
  }

  var data = sheet.getRange(2, 1, lastRow - 1, INV_COLS).getValues();
  trackCellReads((lastRow - 1) * INV_COLS);
  var results = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];

    // Skip if filtering for replenishment and not flagged
    if (replenishOnly && String(row[INV.REPLENISH]).toLowerCase() !== "true") {
      continue;
    }

    // Skip rows with no farmos_name (empty rows)
    if (!String(row[INV.FARMOS_NAME]).trim()) continue;

    results.push(buildSeedResult(row, i + 2));
  }

  return jsonResponse({ success: true, seeds: results, count: results.length });
}

// ── Record transaction ─────────────────────────────────────────

function handleTransaction(body) {
  var user = (body.user || "").trim();
  var seedName = (body.seed_name || "").trim();
  var txnType = (body.type || "").toLowerCase(); // take, add, status_change
  var grams = parseFloat(body.grams) || 0;
  var newStockLevel = body.new_stock_level; // 0, 0.5, 1 (for sachets)
  var replenish = body.replenish === true || body.replenish === "true";
  var notes = (body.notes || "").trim();

  if (!user) {
    return jsonResponse({ success: false, error: "User name is required" });
  }
  if (!seedName) {
    return jsonResponse({ success: false, error: "Seed name is required" });
  }
  if (["take", "add", "status_change"].indexOf(txnType) === -1) {
    return jsonResponse({ success: false, error: "Invalid transaction type: " + txnType + ". Use take, add, or status_change" });
  }

  // Find the seed in inventory by farmos_name
  var invSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(INV_TAB);
  var lastRow = invSheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ success: false, error: "Inventory is empty" });
  }

  var data = invSheet.getRange(2, 1, lastRow - 1, INV_COLS).getValues();
  trackCellReads((lastRow - 1) * INV_COLS);
  var foundRow = -1;
  var previousValue = "";

  for (var i = 0; i < data.length; i++) {
    if (String(data[i][INV.FARMOS_NAME]).trim() === seedName) {
      foundRow = i;
      break;
    }
  }

  if (foundRow === -1) {
    return jsonResponse({ success: false, error: "Seed not found: " + seedName });
  }

  var row = data[foundRow];
  var unit = String(row[INV.UNIT]).toLowerCase();
  var sheetRow = foundRow + 2; // 1-indexed + header

  // Calculate new values and update inventory
  if (unit === "sachet" || unit === "sachet count") {
    // Sachet: update stock_level (column S, index 18)
    previousValue = String(row[INV.STOCK_LEVEL]);
    if (newStockLevel !== undefined && newStockLevel !== null && newStockLevel !== "") {
      var level = parseFloat(newStockLevel);
      invSheet.getRange(sheetRow, INV.STOCK_LEVEL + 1).setValue(level);
      trackCellWrites(1);

      // Auto-flag for replenishment if Empty
      if (level === 0 && !replenish) {
        replenish = true;
      }
    }
  } else {
    // Bulk: update quantity_grams (column R, index 17)
    var currentGrams = parseFloat(row[INV.QTY_GRAMS]) || 0;
    previousValue = String(currentGrams) + "g";
    var newGrams;

    if (txnType === "take") {
      newGrams = Math.max(0, currentGrams - Math.abs(grams));
    } else if (txnType === "add") {
      newGrams = currentGrams + Math.abs(grams);
    }

    if (newGrams !== undefined) {
      invSheet.getRange(sheetRow, INV.QTY_GRAMS + 1).setValue(newGrams);
      trackCellWrites(1);
    }
  }

  // Update replenish flag (column AC, index 28)
  invSheet.getRange(sheetRow, INV.REPLENISH + 1).setValue(replenish ? "TRUE" : "FALSE");
  trackCellWrites(1);

  // Update last_updated (column AD, index 29)
  invSheet.getRange(sheetRow, INV.LAST_UPDATED + 1).setValue(new Date());
  trackCellWrites(1);

  // Log transaction to Transactions tab
  var txnSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TXN_TAB);
  if (!txnSheet) {
    // Create Transactions tab if it doesn't exist
    txnSheet = SpreadsheetApp.getActiveSpreadsheet().insertSheet(TXN_TAB);
    txnSheet.appendRow([
      "Timestamp", "User", "Seed", "Type", "Grams",
      "New Stock Level", "Previous Value", "Replenish Flag", "Notes"
    ]);
  }

  txnSheet.appendRow([
    new Date(),
    user,
    seedName,
    txnType,
    grams || "",
    (newStockLevel !== undefined && newStockLevel !== null) ? newStockLevel : "",
    previousValue,
    replenish ? "TRUE" : "FALSE",
    notes
  ]);
  trackCellWrites(9);

  // Read back updated row for response
  var updatedRow = invSheet.getRange(sheetRow, 1, 1, INV_COLS).getValues()[0];
  trackCellReads(INV_COLS);

  return jsonResponse({
    success: true,
    message: txnType + " recorded for " + seedName + " by " + user,
    seed: buildSeedResult(updatedRow, sheetRow)
  });
}

// ── Build seed result object ───────────────────────────────────

function buildSeedResult(row, rowNum) {
  var unit = String(row[INV.UNIT] || "").toLowerCase();
  var isSachet = unit === "sachet" || unit === "sachet count";

  return {
    row_id: String(rowNum),
    farmos_name: String(row[INV.FARMOS_NAME] || ""),
    common_name: String(row[INV.COMMON_NAME] || ""),
    variety: String(row[INV.VARIETY] || ""),
    source: String(row[INV.SOURCE] || ""),
    quantity_grams: isSachet ? null : (parseFloat(row[INV.QTY_GRAMS]) || 0),
    stock_level: isSachet ? parseFloat(row[INV.STOCK_LEVEL]) || 0 : null,
    unit: isSachet ? "sachet" : "bulk",
    strata: String(row[INV.STRATA] || ""),
    plant_functions: String(row[INV.PLANT_FUNCTIONS] || ""),
    dominant_function: String(row[INV.FUNCTION] || ""),
    season: String(row[INV.SEASON] || ""),
    expiry_date: String(row[INV.EXPIRY] || ""),
    quality: String(row[INV.QUALITY] || ""),
    location: String(row[INV.LOCATION] || "Fridge"),
    germination_time: String(row[INV.GERMINATION_TIME] || ""),
    transplant_days: String(row[INV.TRANSPLANT_DAYS] || ""),
    replenish: String(row[INV.REPLENISH]).toLowerCase() === "true",
    last_updated: row[INV.LAST_UPDATED] ? new Date(row[INV.LAST_UPDATED]).toISOString() : null
  };
}

// ── Utility ────────────────────────────────────────────────────

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
