/**
 * Firefly Corner Farm — Seed Bank QR Page Logic
 *
 * Vanilla JS — no dependencies. Handles:
 * - User name persistence (localStorage)
 * - Seed search with debounced live filtering
 * - Per-row transaction submission (bulk grams / sachet status)
 * - Replenishment flagging (auto-prompted on Empty)
 * - Submission to Google Apps Script backend
 */

// ─── CONFIGURATION ──────────────────────────────────────────

// Endpoint is set via data-endpoint attribute on body element
var ENDPOINT = "";

// ─── INITIALIZATION ──────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  ENDPOINT = document.body.dataset.endpoint || "";

  // Restore user name from localStorage
  var savedName = localStorage.getItem("firefly_seedbank_user") || "";
  var nameInput = document.getElementById("user-name");
  if (nameInput && savedName) {
    nameInput.value = savedName;
  }
  if (nameInput) {
    nameInput.addEventListener("change", function () {
      localStorage.setItem("firefly_seedbank_user", this.value.trim());
    });
  }

  // Search input with debounce
  var searchInput = document.getElementById("seed-search");
  if (searchInput) {
    var debounceTimer = null;
    searchInput.addEventListener("input", function () {
      var q = this.value.trim();
      clearTimeout(debounceTimer);
      if (q.length < 2) {
        clearResults();
        return;
      }
      debounceTimer = setTimeout(function () {
        searchSeeds(q);
      }, 300);
    });
  }
});

// ─── SEARCH ──────────────────────────────────────────────────

function searchSeeds(query) {
  var resultsDiv = document.getElementById("search-results");
  var statusDiv = document.getElementById("search-status");
  if (!resultsDiv) return;

  statusDiv.textContent = "Searching\u2026";
  statusDiv.style.display = "block";
  resultsDiv.innerHTML = "";

  var url = ENDPOINT + "?action=search&query=" + encodeURIComponent(query);

  fetch(url, { redirect: "follow" })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      statusDiv.style.display = "none";
      if (!data.success) {
        statusDiv.textContent = "Error: " + (data.error || "Unknown error");
        statusDiv.style.display = "block";
        return;
      }
      if (data.count === 0) {
        statusDiv.innerHTML = "No seeds found for \u201c" + escHtml(query) + "\u201d \u2014 check spelling or ask James";
        statusDiv.style.display = "block";
        return;
      }
      renderResults(data.seeds);
    })
    .catch(function (err) {
      statusDiv.textContent = "Connection error \u2014 check your internet";
      statusDiv.style.display = "block";
    });
}

function clearResults() {
  var resultsDiv = document.getElementById("search-results");
  var statusDiv = document.getElementById("search-status");
  if (resultsDiv) resultsDiv.innerHTML = "";
  if (statusDiv) statusDiv.style.display = "none";
}

// ─── RENDER RESULTS ──────────────────────────────────────────

function renderResults(seeds) {
  var container = document.getElementById("search-results");
  container.innerHTML = "";

  for (var i = 0; i < seeds.length; i++) {
    container.appendChild(buildSeedCard(seeds[i]));
  }
}

function buildSeedCard(seed) {
  var card = document.createElement("div");
  card.className = "seed-card";
  card.dataset.farmosName = seed.farmos_name;
  card.dataset.unit = seed.unit;
  card.dataset.rowId = seed.row_id;

  var isSachet = seed.unit === "sachet";

  // Display name
  var displayName = seed.farmos_name;
  var varietyLabel = seed.variety ? " (" + seed.variety + ")" : "";

  // Current stock display
  var stockDisplay = "";
  var stockClass = "";
  if (isSachet) {
    var level = parseFloat(seed.stock_level) || 0;
    if (level >= 1) { stockDisplay = "Full"; stockClass = "stock-full"; }
    else if (level >= 0.5) { stockDisplay = "Half"; stockClass = "stock-half"; }
    else { stockDisplay = "Empty"; stockClass = "stock-empty"; }
  } else {
    var grams = parseFloat(seed.quantity_grams) || 0;
    stockDisplay = grams + "g";
    stockClass = grams > 0 ? "stock-full" : "stock-empty";
  }

  // Location
  var location = seed.location || "Fridge";
  var locationIcon = location.toLowerCase() === "freezer" ? "\u2744\ufe0f" : "\ud83c\udf21\ufe0f";

  // Season + function badges
  var badges = "";
  if (seed.season) badges += '<span class="seed-badge season-badge">' + escHtml(seed.season) + '</span>';
  if (seed.dominant_function) badges += '<span class="seed-badge fn-badge">' + escHtml(seed.dominant_function) + '</span>';

  // Strata color mapping
  var strataColors = {
    emergent: '#2d5016', high: '#4a7c29', medium: '#6b9e3c', low: '#8bb85a'
  };
  var strataColor = strataColors[(seed.strata || '').toLowerCase()] || '#9ca3af';

  // Build enrichment detail (collapsible)
  var detailParts = [];
  if (seed.strata) detailParts.push('<span class="seed-strata" style="color:' + strataColor + '">' + escHtml(seed.strata) + ' strata</span>');
  if (seed.germination_time) detailParts.push('<span class="seed-detail-item">\ud83c\udf31 Germ: ' + escHtml(seed.germination_time) + '</span>');
  if (seed.transplant_days) detailParts.push('<span class="seed-detail-item">\ud83c\udf3f Transplant: ' + escHtml(seed.transplant_days) + ' days</span>');
  if (seed.expiry_date) detailParts.push('<span class="seed-detail-item">\ud83d\udcc5 Exp: ' + escHtml(seed.expiry_date) + '</span>');
  if (seed.quality) detailParts.push('<span class="seed-detail-item quality-' + (seed.quality === 'G' ? 'good' : 'bad') + '">' + (seed.quality === 'G' ? '\u2705' : '\u26a0\ufe0f') + ' ' + (seed.quality === 'G' ? 'Good' : 'Poor') + '</span>');

  // Plant functions as pills
  var functionPills = '';
  if (seed.plant_functions) {
    var fns = seed.plant_functions.split(',');
    for (var f = 0; f < fns.length; f++) {
      var fn = fns[f].trim();
      if (fn) functionPills += '<span class="fn-pill fn-' + fn.replace(/_/g, '-') + '">' + fn.replace(/_/g, ' ') + '</span>';
    }
  }

  card.innerHTML =
    '<div class="seed-header" onclick="toggleSeedDetail(this)">' +
      '<div class="seed-info">' +
        '<div class="seed-name">' + escHtml(displayName) + '</div>' +
        (seed.common_name !== seed.farmos_name ? '<div class="seed-botanical">' + escHtml(seed.common_name) + (seed.variety ? ' \u2014 ' + escHtml(seed.variety) : '') + '</div>' : '') +
        (seed.source ? '<div class="seed-source">' + escHtml(seed.source) + '</div>' : '') +
        (badges ? '<div class="seed-badges">' + badges + '</div>' : '') +
      '</div>' +
      '<div class="seed-stock-info">' +
        '<span class="seed-stock ' + stockClass + '">' + stockDisplay + '</span>' +
        '<span class="seed-location">' + locationIcon + ' ' + escHtml(location) + '</span>' +
      '</div>' +
    '</div>' +
    (detailParts.length > 0 || functionPills ?
      '<div class="seed-detail" style="display:none">' +
        (detailParts.length > 0 ? '<div class="seed-detail-row">' + detailParts.join(' ') + '</div>' : '') +
        (functionPills ? '<div class="seed-functions">' + functionPills + '</div>' : '') +
      '</div>' : '') +
    '<div class="seed-transaction">' +
      buildTransactionFields(seed, isSachet) +
    '</div>';

  return card;
}

function buildTransactionFields(seed, isSachet) {
  var id = "txn-" + seed.row_id;

  if (isSachet) {
    var level = parseFloat(seed.stock_level) || 0;
    return '' +
      '<div class="txn-row">' +
        '<label class="txn-label">Update status:</label>' +
        '<div class="sachet-toggle" id="' + id + '-toggle">' +
          '<button type="button" class="sachet-btn' + (level >= 1 ? ' active' : '') + '" data-level="1" onclick="selectSachet(this)">Full</button>' +
          '<button type="button" class="sachet-btn' + (level >= 0.5 && level < 1 ? ' active' : '') + '" data-level="0.5" onclick="selectSachet(this)">Half</button>' +
          '<button type="button" class="sachet-btn' + (level === 0 ? ' active' : '') + '" data-level="0" onclick="selectSachet(this)">Empty</button>' +
        '</div>' +
      '</div>' +
      '<div class="txn-row replenish-row" id="' + id + '-replenish"' + (level === 0 || seed.replenish ? '' : ' style="display:none"') + '>' +
        '<label class="replenish-check">' +
          '<input type="checkbox" id="' + id + '-replenish-cb"' + (level === 0 || seed.replenish ? ' checked' : '') + '>' +
          ' Flag for replenishment' +
        '</label>' +
      '</div>' +
      '<div class="txn-row">' +
        '<input type="text" class="txn-notes" id="' + id + '-notes" placeholder="Notes (optional)">' +
      '</div>' +
      '<div class="txn-row">' +
        '<button type="button" class="txn-submit" onclick="submitTransaction(\'' + escAttr(seed.farmos_name) + '\', \'' + seed.row_id + '\', \'sachet\')">Submit</button>' +
      '</div>';
  } else {
    // Bulk seeds — grams taken/added
    return '' +
      '<div class="txn-row txn-grams-row">' +
        '<div class="txn-grams-group">' +
          '<label class="txn-label">Grams taken:</label>' +
          '<input type="number" class="txn-grams" id="' + id + '-take" min="0" step="1" placeholder="0">' +
        '</div>' +
        '<div class="txn-grams-group">' +
          '<label class="txn-label">Grams added:</label>' +
          '<input type="number" class="txn-grams" id="' + id + '-add" min="0" step="1" placeholder="0">' +
        '</div>' +
      '</div>' +
      '<div class="txn-row replenish-row">' +
        '<label class="replenish-check">' +
          '<input type="checkbox" id="' + id + '-replenish-cb"' + (seed.replenish ? ' checked' : '') + '>' +
          ' Flag for replenishment' +
        '</label>' +
      '</div>' +
      '<div class="txn-row">' +
        '<input type="text" class="txn-notes" id="' + id + '-notes" placeholder="Notes (optional, e.g. \u201cfarm-saved P2R3\u201d)">' +
      '</div>' +
      '<div class="txn-row">' +
        '<button type="button" class="txn-submit" onclick="submitTransaction(\'' + escAttr(seed.farmos_name) + '\', \'' + seed.row_id + '\', \'bulk\')">Submit</button>' +
      '</div>';
  }
}

// ─── SACHET TOGGLE ───────────────────────────────────────────

function selectSachet(btn) {
  // Deactivate siblings
  var siblings = btn.parentElement.querySelectorAll(".sachet-btn");
  for (var i = 0; i < siblings.length; i++) {
    siblings[i].classList.remove("active");
  }
  btn.classList.add("active");

  // Show/check replenish if Empty
  var level = parseFloat(btn.dataset.level);
  var card = btn.closest(".seed-card");
  var rowId = card.dataset.rowId;
  var replenishRow = document.getElementById("txn-" + rowId + "-replenish");
  var replenishCb = document.getElementById("txn-" + rowId + "-replenish-cb");

  if (level === 0) {
    replenishRow.style.display = "";
    replenishCb.checked = true;
    // Show warning
    showEmptyWarning(card);
  } else {
    replenishRow.style.display = "none";
  }
}

function showEmptyWarning(card) {
  // Remove existing warning if any
  var existing = card.querySelector(".empty-warning");
  if (existing) existing.remove();

  var warning = document.createElement("div");
  warning.className = "empty-warning";
  warning.innerHTML = '\u26a0\ufe0f This seed is now empty. Please confirm the replenishment flag is checked before submitting.';
  card.querySelector(".seed-transaction").insertBefore(warning, card.querySelector(".txn-submit").closest(".txn-row"));
}

// ─── SUBMIT TRANSACTION ──────────────────────────────────────

function submitTransaction(seedName, rowId, unit) {
  var userName = (document.getElementById("user-name").value || "").trim();
  if (!userName) {
    showFeedback("Please enter your name before submitting.", "error");
    document.getElementById("user-name").focus();
    return;
  }

  var prefix = "txn-" + rowId;
  var notes = (document.getElementById(prefix + "-notes").value || "").trim();
  var replenish = document.getElementById(prefix + "-replenish-cb").checked;

  var payload = {
    action: "transaction",
    user: userName,
    seed_name: seedName,
    replenish: replenish,
    notes: notes
  };

  if (unit === "sachet") {
    // Get selected sachet level
    var card = document.querySelector('.seed-card[data-row-id="' + rowId + '"]');
    var activeBtn = card.querySelector(".sachet-btn.active");
    if (!activeBtn) {
      showFeedback("Please select a sachet status (Full / Half / Empty).", "error");
      return;
    }
    payload.type = "status_change";
    payload.new_stock_level = parseFloat(activeBtn.dataset.level);

    // Enforce replenish on Empty
    if (payload.new_stock_level === 0 && !replenish) {
      showFeedback("This seed is empty \u2014 please tick \u2018Flag for replenishment\u2019 before submitting.", "error");
      return;
    }
  } else {
    // Bulk — determine take or add
    var takeVal = parseFloat(document.getElementById(prefix + "-take").value) || 0;
    var addVal = parseFloat(document.getElementById(prefix + "-add").value) || 0;

    if (takeVal === 0 && addVal === 0) {
      showFeedback("Please enter grams taken or added.", "error");
      return;
    }
    if (takeVal > 0 && addVal > 0) {
      showFeedback("Please enter either grams taken or grams added, not both.", "error");
      return;
    }

    payload.type = takeVal > 0 ? "take" : "add";
    payload.grams = takeVal > 0 ? takeVal : addVal;
  }

  // Disable submit button
  var submitBtn = document.querySelector('.seed-card[data-row-id="' + rowId + '"] .txn-submit');
  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting\u2026";

  fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: JSON.stringify(payload),
    redirect: "follow"
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showFeedback(data.message || "Transaction recorded!", "success");
        // Update the card with new stock info
        if (data.seed) {
          updateCardStock(rowId, data.seed);
        }
        // Clear transaction fields
        clearTransactionFields(rowId, unit);
      } else {
        showFeedback("Error: " + (data.error || "Unknown error"), "error");
      }
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit";
    })
    .catch(function (err) {
      showFeedback("Connection error \u2014 please try again", "error");
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit";
    });
}

// ─── UI HELPERS ──────────────────────────────────────────────

function updateCardStock(rowId, seed) {
  var card = document.querySelector('.seed-card[data-row-id="' + rowId + '"]');
  if (!card) return;

  var stockEl = card.querySelector(".seed-stock");
  if (!stockEl) return;

  // Remove all stock classes
  stockEl.classList.remove("stock-full", "stock-half", "stock-empty");

  if (seed.unit === "sachet") {
    var level = parseFloat(seed.stock_level) || 0;
    if (level >= 1) { stockEl.textContent = "Full"; stockEl.classList.add("stock-full"); }
    else if (level >= 0.5) { stockEl.textContent = "Half"; stockEl.classList.add("stock-half"); }
    else { stockEl.textContent = "Empty"; stockEl.classList.add("stock-empty"); }
  } else {
    var grams = parseFloat(seed.quantity_grams) || 0;
    stockEl.textContent = grams + "g";
    stockEl.classList.add(grams > 0 ? "stock-full" : "stock-empty");
  }
}

function clearTransactionFields(rowId, unit) {
  var prefix = "txn-" + rowId;
  var notes = document.getElementById(prefix + "-notes");
  if (notes) notes.value = "";

  if (unit === "bulk") {
    var take = document.getElementById(prefix + "-take");
    var add = document.getElementById(prefix + "-add");
    if (take) take.value = "";
    if (add) add.value = "";
  }

  // Remove any empty warning
  var card = document.querySelector('.seed-card[data-row-id="' + rowId + '"]');
  if (card) {
    var warning = card.querySelector(".empty-warning");
    if (warning) warning.remove();
  }
}

function showFeedback(message, type) {
  // Remove existing feedback
  var existing = document.querySelector(".feedback-toast");
  if (existing) existing.remove();

  var toast = document.createElement("div");
  toast.className = "feedback-toast feedback-" + type;
  toast.textContent = message;
  document.body.appendChild(toast);

  // Auto-dismiss after 4s
  setTimeout(function () {
    toast.classList.add("fade-out");
    setTimeout(function () { toast.remove(); }, 300);
  }, 4000);
}

function escHtml(str) {
  var div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function escAttr(str) {
  return (str || "").replace(/'/g, "\\'").replace(/"/g, "&quot;");
}

// ─── DETAIL TOGGLE ────────────────────────────────────────────

function toggleSeedDetail(headerEl) {
  var card = headerEl.closest(".seed-card");
  var detail = card.querySelector(".seed-detail");
  if (!detail) return;
  detail.style.display = detail.style.display === "none" ? "block" : "none";
}
