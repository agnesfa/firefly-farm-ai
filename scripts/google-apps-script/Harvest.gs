// Harvest.gs — bound to "Firefly Corner - Harvest Log" Sheet
// Deploy as: Web app, Execute as: Me, Access: Anyone
//
// Receives POST from harvest.js with payload:
//   { action: "harvest", submission_id, harvester, timestamp, species,
//     weight_grams, location, notes, photo }
//
// Columns: submission_id | timestamp | received_at | harvester | species |
//          weight_grams | location | notes | photo_url | status

var SHEET_NAME = "Harvests";
var DRIVE_FOLDER_ID = "1vI_JxVYnTAcclFOT5ziN7wBTz6ofuskA";

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    if (data.action !== "harvest") {
      return ContentService.createTextOutput(JSON.stringify({success: false, error: "Unknown action"}))
        .setMimeType(ContentService.MimeType.JSON);
    }
    return ContentService.createTextOutput(JSON.stringify(handleHarvest(data)))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({success: false, error: err.message}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) || "health";
  if (action === "health") {
    return ContentService.createTextOutput(JSON.stringify({
      status: "ok", service: "harvest", timestamp: new Date().toISOString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
  return ContentService.createTextOutput(JSON.stringify({error: "Unknown action"}))
    .setMimeType(ContentService.MimeType.JSON);
}

function handleHarvest(data) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(["submission_id", "timestamp", "received_at", "harvester",
                     "species", "weight_grams", "location", "notes", "photo_url", "status"]);
  }

  // Dedup check
  var ids = sheet.getRange("A:A").getValues().flat();
  if (ids.indexOf(data.submission_id) !== -1) {
    return {success: true, message: "Duplicate — already recorded"};
  }

  // Save photo to Drive if present
  var photoUrl = "";
  if (data.photo && DRIVE_FOLDER_ID) {
    try {
      var folder = DriveApp.getFolderById(DRIVE_FOLDER_ID);
      var base64 = data.photo.replace(/^data:image\/\w+;base64,/, "");
      var blob = Utilities.newBlob(Utilities.base64Decode(base64), "image/jpeg",
        data.submission_id + ".jpg");
      var file = folder.createFile(blob);
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      photoUrl = file.getUrl();
    } catch (photoErr) {
      Logger.log("Photo save failed: " + photoErr.message);
    }
  }

  sheet.appendRow([
    data.submission_id,
    data.timestamp,
    new Date().toISOString(),
    data.harvester || "",
    data.species || "",
    data.weight_grams || 0,
    data.location || "",
    data.notes || "",
    photoUrl,
    "new"
  ]);

  return {success: true, message: "Harvest recorded"};
}
