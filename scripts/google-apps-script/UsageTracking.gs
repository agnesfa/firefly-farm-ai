/**
 * Firefly Corner — Apps Script Usage Tracking Utility
 *
 * Add this file alongside any Apps Script backend (TeamMemory.gs,
 * PlantTypes.gs, KnowledgeBase.gs, SeedBank.gs, Code.gs).
 *
 * Provides:
 *   - Per-execution usage counter (daily reset)
 *   - Cell read/write estimation
 *   - Health check with quota warnings
 *
 * Usage:
 *   1. Paste this file into each Apps Script project
 *   2. Call trackExecution() at the start of doGet/doPost
 *   3. Call trackCellReads(count) after sheet reads
 *   4. Add ?action=health to doGet handler → return handleHealth()
 *
 * Google Apps Script quotas (consumer/free account):
 *   - Script executions: 5,000/day (was 20,000 for Workspace)
 *   - URL fetch calls: 20,000/day
 *   - Spreadsheet read cells: ~100,000/day (undocumented soft limit)
 *   - Script runtime: 6 min per execution
 *   - Properties storage: 500KB
 *   - Triggers: 20/user
 *
 * WARNING thresholds (80% of limit):
 *   - Executions: 4,000/day
 *   - Cell reads: 80,000/day
 */

// ── Usage Tracking ─────────────────────────────────────────────

/**
 * Track one script execution. Call at start of doGet/doPost.
 */
function trackExecution() {
  try {
    var props = PropertiesService.getScriptProperties();
    var today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
    var key = "usage_" + today;

    var usage = JSON.parse(props.getProperty(key) || "{}");
    usage.executions = (usage.executions || 0) + 1;
    usage.cell_reads = usage.cell_reads || 0;
    usage.cell_writes = usage.cell_writes || 0;
    usage.date = today;

    props.setProperty(key, JSON.stringify(usage));

    // Clean up old days (keep last 7)
    cleanOldUsage_(props, today);
  } catch (e) {
    // Never let tracking break the actual request
  }
}

/**
 * Track cell reads after a sheet range read.
 * @param {number} cellCount - Number of cells read (rows * cols)
 */
function trackCellReads(cellCount) {
  try {
    var props = PropertiesService.getScriptProperties();
    var today = new Date().toISOString().slice(0, 10);
    var key = "usage_" + today;

    var usage = JSON.parse(props.getProperty(key) || "{}");
    usage.cell_reads = (usage.cell_reads || 0) + cellCount;
    props.setProperty(key, JSON.stringify(usage));
  } catch (e) {
    // Silent fail
  }
}

/**
 * Track cell writes after a sheet write.
 * @param {number} cellCount - Number of cells written
 */
function trackCellWrites(cellCount) {
  try {
    var props = PropertiesService.getScriptProperties();
    var today = new Date().toISOString().slice(0, 10);
    var key = "usage_" + today;

    var usage = JSON.parse(props.getProperty(key) || "{}");
    usage.cell_writes = (usage.cell_writes || 0) + cellCount;
    props.setProperty(key, JSON.stringify(usage));
  } catch (e) {
    // Silent fail
  }
}

// ── Health Check ───────────────────────────────────────────────

/**
 * Handle ?action=health request. Returns status + usage + warnings.
 * Add to doGet: if (action === "health") return handleHealth();
 */
function handleHealth() {
  var props = PropertiesService.getScriptProperties();
  var today = new Date().toISOString().slice(0, 10);
  var key = "usage_" + today;

  var usage = JSON.parse(props.getProperty(key) || "{}");
  var executions = usage.executions || 0;
  var cellReads = usage.cell_reads || 0;
  var cellWrites = usage.cell_writes || 0;

  // Quota limits (consumer account)
  var EXEC_LIMIT = 5000;
  var CELL_READ_LIMIT = 100000;
  var EXEC_WARN = 4000;   // 80%
  var CELL_READ_WARN = 80000; // 80%

  var warnings = [];
  var status = "ok";

  if (executions >= EXEC_LIMIT) {
    status = "error";
    warnings.push("EXCEEDED: " + executions + "/" + EXEC_LIMIT + " daily executions");
  } else if (executions >= EXEC_WARN) {
    status = "warning";
    warnings.push("HIGH: " + executions + "/" + EXEC_LIMIT + " daily executions (" + Math.round(executions/EXEC_LIMIT*100) + "%)");
  }

  if (cellReads >= CELL_READ_LIMIT) {
    status = "error";
    warnings.push("EXCEEDED: " + cellReads + "/" + CELL_READ_LIMIT + " daily cell reads");
  } else if (cellReads >= CELL_READ_WARN) {
    if (status !== "error") status = "warning";
    warnings.push("HIGH: " + cellReads + "/" + CELL_READ_LIMIT + " daily cell reads (" + Math.round(cellReads/CELL_READ_LIMIT*100) + "%)");
  }

  // Get last 7 days of usage for trend
  var history = [];
  for (var d = 6; d >= 0; d--) {
    var date = new Date();
    date.setDate(date.getDate() - d);
    var dateStr = date.toISOString().slice(0, 10);
    var dayKey = "usage_" + dateStr;
    var dayUsage = JSON.parse(props.getProperty(dayKey) || "{}");
    if (dayUsage.executions || dayUsage.cell_reads) {
      history.push({
        date: dateStr,
        executions: dayUsage.executions || 0,
        cell_reads: dayUsage.cell_reads || 0,
        cell_writes: dayUsage.cell_writes || 0
      });
    }
  }

  return jsonResponse({
    success: true,
    status: status,
    service: ScriptApp.getScriptId() ? "apps-script" : "unknown",
    today: {
      date: today,
      executions: executions,
      executions_limit: EXEC_LIMIT,
      executions_pct: Math.round(executions / EXEC_LIMIT * 100),
      cell_reads: cellReads,
      cell_reads_limit: CELL_READ_LIMIT,
      cell_reads_pct: Math.round(cellReads / CELL_READ_LIMIT * 100),
      cell_writes: cellWrites
    },
    warnings: warnings,
    history: history
  });
}

// ── Internal helpers ───────────────────────────────────────────

/**
 * Remove usage entries older than 7 days to stay within PropertiesService limits.
 */
function cleanOldUsage_(props, today) {
  try {
    var allKeys = props.getKeys();
    var cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 8);
    var cutoffStr = cutoff.toISOString().slice(0, 10);

    for (var i = 0; i < allKeys.length; i++) {
      if (allKeys[i].indexOf("usage_") === 0) {
        var dateStr = allKeys[i].replace("usage_", "");
        if (dateStr < cutoffStr) {
          props.deleteProperty(allKeys[i]);
        }
      }
    }
  } catch (e) {
    // Silent fail
  }
}
