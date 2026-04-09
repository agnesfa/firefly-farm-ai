/**
 * Firefly Corner Farm — Field Observation Page Logic
 *
 * Vanilla JS — no dependencies. Handles:
 * - Observer name persistence (localStorage)
 * - Quick observation and full inventory modes
 * - Form data collection and submission to Google Apps Script
 * - Status feedback (success/error/offline)
 * - Photo capture with client-side compression (Phase B)
 * - Offline queue with IndexedDB (Phase B)
 */

// ─── INITIALIZATION ──────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  initObservePage();
});

function initObservePage() {
  // Restore observer name from localStorage
  var savedName = localStorage.getItem("firefly_observer_name") || "";
  var nameInput = document.getElementById("observer-name");
  if (nameInput && savedName) {
    nameInput.value = savedName;
  }

  // Save name on change
  if (nameInput) {
    nameInput.addEventListener("change", function () {
      localStorage.setItem("firefly_observer_name", this.value.trim());
    });
  }

  // Set current date/time
  var dtInput = document.getElementById("obs-datetime");
  if (dtInput) {
    var now = new Date();
    // Format as local datetime-local value (YYYY-MM-DDTHH:MM)
    var offset = now.getTimezoneOffset();
    var local = new Date(now.getTime() - offset * 60000);
    dtInput.value = local.toISOString().slice(0, 16);
  }

  // Mode toggle
  var modeToggle = document.querySelectorAll(".mode-tab");
  modeToggle.forEach(function (tab) {
    tab.addEventListener("click", function () {
      switchMode(this.dataset.mode);
    });
  });

  // Quick mode: species selector
  var speciesSelect = document.getElementById("quick-species");
  if (speciesSelect) {
    speciesSelect.addEventListener("change", function () {
      updateQuickPlantInfo(this.value);
    });
  }

  // Submit buttons
  var quickSubmit = document.getElementById("quick-submit");
  if (quickSubmit) {
    quickSubmit.addEventListener("click", function (e) {
      e.preventDefault();
      submitQuickObservation();
    });
  }

  var inventorySubmit = document.getElementById("inventory-submit");
  if (inventorySubmit) {
    inventorySubmit.addEventListener("click", function (e) {
      e.preventDefault();
      submitInventoryObservation();
    });
  }

  // Section comment submit
  var commentSubmit = document.getElementById("comment-submit");
  if (commentSubmit) {
    commentSubmit.addEventListener("click", function (e) {
      e.preventDefault();
      submitSectionComment();
    });
  }

  // Add New Plant panel
  var plantCloseBtn = document.getElementById("add-plant-close");
  if (plantCloseBtn) {
    plantCloseBtn.addEventListener("click", function () {
      hideAddPlantPanel();
    });
  }

  var plantSearch = document.getElementById("plant-search");
  if (plantSearch) {
    plantSearch.addEventListener("input", function () {
      filterPlantTypes(this.value);
    });
  }

  var newPlantSubmit = document.getElementById("new-plant-submit");
  if (newPlantSubmit) {
    newPlantSubmit.addEventListener("click", function (e) {
      e.preventDefault();
      submitNewPlantObservation();
    });
  }

  // Photo capture handlers
  initPhotoCapture();

  // PlantNet "What is this plant?" identification
  initPlantNetIdentify();

  // Show quick mode by default
  switchMode("quick");
}

// ─── MODE SWITCHING ──────────────────────────────────────────

function switchMode(mode) {
  var quickPanel = document.getElementById("mode-quick");
  var inventoryPanel = document.getElementById("mode-inventory");
  var commentPanel = document.getElementById("mode-comment");
  var tabs = document.querySelectorAll(".mode-tab");

  tabs.forEach(function (tab) {
    tab.classList.toggle("active", tab.dataset.mode === mode);
  });

  if (quickPanel) quickPanel.style.display = mode === "quick" ? "block" : "none";
  if (inventoryPanel) inventoryPanel.style.display = mode === "inventory" ? "block" : "none";
  if (commentPanel) commentPanel.style.display = mode === "comment" ? "block" : "none";

  // Hide add-plant panel when switching modes
  hideAddPlantPanel();
}

// ─── QUICK OBSERVATION ──────────────────────────────────────

function updateQuickPlantInfo(species) {
  var infoDiv = document.getElementById("quick-plant-info");
  if (!infoDiv || !species) {
    if (infoDiv) infoDiv.innerHTML = "";
    return;
  }

  // Handle Unknown Plant selection
  if (species === "Unknown") {
    infoDiv.innerHTML =
      '<div class="quick-info-row">' +
      '<span class="quick-info-label">Unknown plant</span> ' +
      '<span class="quick-info-value">Describe in notes + add photo</span>' +
      "</div>";
    return;
  }

  // Find plant data from embedded SECTION_DATA
  var plant = null;
  if (typeof SECTION_DATA !== "undefined" && SECTION_DATA.plants) {
    for (var i = 0; i < SECTION_DATA.plants.length; i++) {
      if (SECTION_DATA.plants[i].species === species) {
        plant = SECTION_DATA.plants[i];
        break;
      }
    }
  }

  if (plant) {
    infoDiv.innerHTML =
      '<div class="quick-info-row">' +
      '<span class="quick-info-label">Current count:</span> ' +
      '<span class="quick-info-value">' + (plant.count || 0) + '</span>' +
      "</div>" +
      '<div class="quick-info-row">' +
      '<span class="quick-info-label">Strata:</span> ' +
      '<span class="quick-info-value">' + (plant.strata || "—") + '</span>' +
      "</div>";
  }
}

function collectQuickData() {
  var species = document.getElementById("quick-species");
  var count = document.getElementById("quick-count");
  var condition = document.getElementById("quick-condition");
  var notes = document.getElementById("quick-notes");
  var sectionNotes = document.getElementById("section-notes-quick");

  if (!species || !species.value) {
    showStatus("error", "Please select a plant species.");
    return null;
  }

  var isUnknown = species.value === "Unknown";

  // Find plant info from SECTION_DATA (not applicable for Unknown)
  var plant = null;
  if (!isUnknown && typeof SECTION_DATA !== "undefined" && SECTION_DATA.plants) {
    for (var i = 0; i < SECTION_DATA.plants.length; i++) {
      if (SECTION_DATA.plants[i].species === species.value) {
        plant = SECTION_DATA.plants[i];
        break;
      }
    }
  }

  var obs = {
    species: species.value,
    strata: plant ? plant.strata : "",
    previous_count: isUnknown ? 0 : (plant ? (plant.count || 0) : 0),
    condition: condition ? condition.value : "alive",
    notes: notes ? notes.value.trim() : "",
  };

  // Only include new_count if the user entered one
  if (count && count.value !== "") {
    obs.new_count = parseFloat(count.value);
  }

  return {
    observations: [obs],
    section_notes: sectionNotes ? sectionNotes.value.trim() : "",
    mode: "quick",
  };
}

function submitQuickObservation() {
  var data = collectQuickData();
  if (!data) return;
  submitObservation(data);
}

// ─── FULL INVENTORY ──────────────────────────────────────────

function collectInventoryData() {
  var rows = document.querySelectorAll(".inv-plant-row");
  var observations = [];

  rows.forEach(function (row) {
    var countInput = row.querySelector(".inv-count-input");
    var noteInput = row.querySelector(".inv-note-input");
    var conditionSelect = row.querySelector(".inv-condition");

    // Only include plants where the observer entered something
    var hasCount = countInput && countInput.value !== "";
    var hasNote = noteInput && noteInput.value.trim() !== "";
    var hasCondition = conditionSelect && conditionSelect.value !== "alive";

    if (hasCount || hasNote || hasCondition) {
      var obs = {
        species: row.dataset.species,
        strata: row.dataset.strata,
        previous_count: parseFloat(row.dataset.current) || 0,
        condition: conditionSelect ? conditionSelect.value : "alive",
        notes: noteInput ? noteInput.value.trim() : "",
      };

      if (hasCount) {
        obs.new_count = parseFloat(countInput.value);
      }

      observations.push(obs);
    }
  });

  if (observations.length === 0) {
    showStatus("error", "No changes recorded. Update at least one plant count or note.");
    return null;
  }

  var sectionNotes = document.getElementById("section-notes-inventory");
  return {
    observations: observations,
    section_notes: sectionNotes ? sectionNotes.value.trim() : "",
    mode: "inventory",
  };
}

function submitInventoryObservation() {
  var data = collectInventoryData();
  if (!data) return;
  submitObservation(data);
}

// ─── SECTION COMMENT ──────────────────────────────────────────

function submitSectionComment() {
  var commentNotes = document.getElementById("comment-notes");
  if (!commentNotes || !commentNotes.value.trim()) {
    showStatus("error", "Please enter a section note.");
    return;
  }

  submitObservation({
    observations: [],
    section_notes: commentNotes.value.trim(),
    mode: "comment",
  });
}

// ─── ADD NEW PLANT ──────────────────────────────────────────

function showAddPlantPanel() {
  var panel = document.getElementById("add-plant-panel");
  if (panel) {
    panel.style.display = "block";
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    var searchInput = document.getElementById("plant-search");
    if (searchInput) {
      searchInput.value = "";
      searchInput.focus();
    }
    // Reset fields
    var fieldsDiv = document.getElementById("new-plant-fields");
    if (fieldsDiv) fieldsDiv.style.display = "none";
    var resultsDiv = document.getElementById("plant-search-results");
    if (resultsDiv) {
      resultsDiv.style.display = "none";
      resultsDiv.innerHTML = "";
    }
  }
}

function hideAddPlantPanel() {
  var panel = document.getElementById("add-plant-panel");
  if (panel) panel.style.display = "none";
  var searchInput = document.getElementById("plant-search");
  if (searchInput) searchInput.value = "";
  var resultsDiv = document.getElementById("plant-search-results");
  if (resultsDiv) {
    resultsDiv.style.display = "none";
    resultsDiv.innerHTML = "";
  }
  var fieldsDiv = document.getElementById("new-plant-fields");
  if (fieldsDiv) fieldsDiv.style.display = "none";
}

function filterPlantTypes(query) {
  var resultsDiv = document.getElementById("plant-search-results");
  if (!resultsDiv) return;

  query = query.trim().toLowerCase();
  if (query.length < 2) {
    resultsDiv.style.display = "none";
    resultsDiv.innerHTML = "";
    return;
  }

  // Filter from PLANT_TYPES_DATA (embedded in page)
  var plantTypes = typeof PLANT_TYPES_DATA !== "undefined" ? PLANT_TYPES_DATA : [];
  var matches = [];
  for (var i = 0; i < plantTypes.length; i++) {
    var pt = plantTypes[i];
    var speciesLower = (pt.species || "").toLowerCase();
    var botanicalLower = (pt.botanical || "").toLowerCase();
    if (speciesLower.indexOf(query) !== -1 || botanicalLower.indexOf(query) !== -1) {
      matches.push(pt);
      if (matches.length >= 15) break;
    }
  }

  if (matches.length === 0) {
    resultsDiv.innerHTML =
      '<div class="plant-search-result" style="color:#9ca3af;cursor:default">No matches found</div>';
    resultsDiv.style.display = "block";
    return;
  }

  var html = "";
  for (var j = 0; j < matches.length; j++) {
    var m = matches[j];
    var escapedSpecies = escapeHtml(m.species);
    var escapedBotanical = escapeHtml(m.botanical || "");
    var escapedStrata = escapeHtml(m.strata || "");
    html +=
      '<div class="plant-search-result" data-species="' + escapedSpecies +
      '" data-strata="' + escapedStrata +
      '" data-botanical="' + escapedBotanical +
      '" onclick="selectNewPlant(this)">' +
      '<div class="search-species">' + escapedSpecies + '</div>' +
      '<div class="search-meta">' + escapedBotanical +
      (escapedStrata ? " · " + escapedStrata : "") + '</div>' +
      '</div>';
  }

  resultsDiv.innerHTML = html;
  resultsDiv.style.display = "block";
}

function selectNewPlant(el) {
  var species = el.dataset.species;
  var strata = el.dataset.strata;

  // Show selection in display fields
  var speciesDisplay = document.getElementById("new-plant-species");
  var strataDisplay = document.getElementById("new-plant-strata");
  if (speciesDisplay) speciesDisplay.textContent = species;
  if (strataDisplay) strataDisplay.textContent = strata || "—";

  // Store selection data
  var fieldsDiv = document.getElementById("new-plant-fields");
  if (fieldsDiv) {
    fieldsDiv.style.display = "block";
    fieldsDiv.dataset.selectedSpecies = species;
    fieldsDiv.dataset.selectedStrata = strata;
  }

  // Hide search results
  var resultsDiv = document.getElementById("plant-search-results");
  if (resultsDiv) resultsDiv.style.display = "none";

  // Update search input with selection
  var searchInput = document.getElementById("plant-search");
  if (searchInput) searchInput.value = species;

  // Focus count input
  var countInput = document.getElementById("new-plant-count");
  if (countInput) countInput.focus();
}

function submitNewPlantObservation() {
  var fieldsDiv = document.getElementById("new-plant-fields");
  if (!fieldsDiv || !fieldsDiv.dataset.selectedSpecies) {
    showStatus("error", "Please search and select a plant species first.");
    return;
  }

  var countInput = document.getElementById("new-plant-count");
  var conditionSelect = document.getElementById("new-plant-condition");
  var notesInput = document.getElementById("new-plant-notes");

  var obs = {
    species: fieldsDiv.dataset.selectedSpecies,
    strata: fieldsDiv.dataset.selectedStrata || "",
    previous_count: 0,
    new_count: countInput && countInput.value !== "" ? parseFloat(countInput.value) : null,
    condition: conditionSelect ? conditionSelect.value : "alive",
    notes: notesInput ? notesInput.value.trim() : "",
    is_new_plant: true,
  };

  if (obs.new_count === null) {
    showStatus("error", "Please enter the count for the new plant.");
    return;
  }

  submitObservation({
    observations: [obs],
    section_notes: "",
    mode: "new_plant",
  });
}

function escapeHtml(text) {
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ─── SUBMISSION ──────────────────────────────────────────────

function submitObservation(formData) {
  var nameInput = document.getElementById("observer-name");
  var dtInput = document.getElementById("obs-datetime");

  if (!nameInput || !nameInput.value.trim()) {
    showStatus("error", "Please enter your name.");
    nameInput && nameInput.focus();
    return;
  }

  // Save observer name
  localStorage.setItem("firefly_observer_name", nameInput.value.trim());

  // Build full payload
  var payload = {
    version: "1",
    submission_id: generateUUID(),
    section_id: typeof SECTION_DATA !== "undefined" ? SECTION_DATA.id : "",
    observer: nameInput.value.trim(),
    timestamp: dtInput ? new Date(dtInput.value).toISOString() : new Date().toISOString(),
    mode: formData.mode,
    observations: formData.observations,
    section_notes: formData.section_notes,
    media: collectMediaData(),
  };

  // Check for endpoint
  if (typeof OBSERVE_ENDPOINT === "undefined" || !OBSERVE_ENDPOINT) {
    showStatus("error", "Observation endpoint not configured. Contact Agnes.");
    return;
  }

  showStatus("sending", "Sending observation...");
  disableSubmitButtons(true);

  // POST to Google Apps Script (text/plain to avoid CORS preflight)
  fetch(OBSERVE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: JSON.stringify(payload),
    redirect: "follow",
  })
    .then(function (response) {
      // Google Apps Script redirects on POST; response may be opaque
      if (response.ok || response.type === "opaque" || response.redirected) {
        return response.text().catch(function () {
          return '{"success": true}';
        });
      }
      throw new Error("Server returned " + response.status);
    })
    .then(function (text) {
      var result;
      try {
        result = JSON.parse(text);
      } catch (e) {
        // Google Apps Script sometimes returns HTML on redirect
        result = { success: true };
      }

      if (result.success) {
        showStatus(
          "success",
          "✓ Observation saved!" +
            (result.duplicate ? " (already recorded)" : "") +
            (result.message ? " " + result.message : "")
        );
        resetForm(formData.mode);
      } else {
        showStatus("error", "Error: " + (result.error || "Unknown error"));
      }
    })
    .catch(function (err) {
      if (!navigator.onLine) {
        // Offline — save to local queue
        saveToLocalQueue(payload);
        showStatus(
          "offline",
          "📱 Saved locally — will sync when back online."
        );
        resetForm(formData.mode);
      } else {
        showStatus("error", "Failed to send: " + err.message + ". Try again.");
      }
    })
    .finally(function () {
      disableSubmitButtons(false);
    });
}

// ─── PHOTO CAPTURE ───────────────────────────────────────────

function initPhotoCapture() {
  var photoInputs = document.querySelectorAll(".obs-photo-input");
  photoInputs.forEach(function (input) {
    input.addEventListener("change", function (e) {
      handlePhotoCapture(e.target);
    });
  });
}

function handlePhotoCapture(input) {
  var file = input.files && input.files[0];
  if (!file) return;

  var previewContainer = input
    .closest(".obs-media-area")
    .querySelector(".obs-photo-previews");
  if (!previewContainer) return;

  // Compress and show preview
  compressImage(file, 1200, 0.7, function (dataUrl) {
    var previewDiv = document.createElement("div");
    previewDiv.className = "obs-photo-preview";
    previewDiv.innerHTML =
      '<img src="' + dataUrl + '" alt="Photo preview">' +
      '<button class="obs-photo-remove" onclick="this.parentElement.remove()" aria-label="Remove photo">✕</button>';
    previewDiv.dataset.base64 = dataUrl;
    previewDiv.dataset.target = input.dataset.target || "section";
    previewContainer.appendChild(previewDiv);

    // Reset input so the same file can be re-selected
    input.value = "";
  });
}

/**
 * Compress an image file using canvas.
 * maxDim: max pixels on the longest side
 * quality: JPEG quality (0-1)
 */
function compressImage(file, maxDim, quality, callback) {
  var reader = new FileReader();
  reader.onload = function (e) {
    var img = new Image();
    img.onload = function () {
      var canvas = document.createElement("canvas");
      var w = img.width;
      var h = img.height;

      if (w > maxDim || h > maxDim) {
        if (w > h) {
          h = Math.round((h * maxDim) / w);
          w = maxDim;
        } else {
          w = Math.round((w * maxDim) / h);
          h = maxDim;
        }
      }

      canvas.width = w;
      canvas.height = h;
      var ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, w, h);

      callback(canvas.toDataURL("image/jpeg", quality));
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function collectMediaData() {
  var media = [];
  var previews = document.querySelectorAll(".obs-photo-preview");
  var counter = 1;

  previews.forEach(function (preview) {
    if (preview.dataset.base64) {
      var sectionId =
        typeof SECTION_DATA !== "undefined" ? SECTION_DATA.id : "unknown";
      media.push({
        type: "photo",
        target: preview.dataset.target || "section",
        filename:
          sectionId +
          "_" +
          (preview.dataset.target || "section") +
          "_" +
          String(counter).padStart(3, "0") +
          ".jpg",
        data: preview.dataset.base64,
      });
      counter++;
    }
  });

  return media;
}

// ─── OFFLINE QUEUE ───────────────────────────────────────────

function saveToLocalQueue(payload) {
  try {
    var queue = JSON.parse(localStorage.getItem("firefly_obs_queue") || "[]");
    // Strip media from localStorage (too large) — only save text data offline
    var lightPayload = JSON.parse(JSON.stringify(payload));
    lightPayload.media = [];
    lightPayload._offline = true;
    queue.push(lightPayload);
    localStorage.setItem("firefly_obs_queue", JSON.stringify(queue));
    updateQueueBanner();
  } catch (e) {
    console.error("Failed to save to local queue:", e);
  }
}

function syncPendingQueue() {
  var queue = JSON.parse(localStorage.getItem("firefly_obs_queue") || "[]");
  if (queue.length === 0) return;

  showStatus("sending", "Syncing " + queue.length + " pending observation(s)...");

  var remaining = [];
  var promises = queue.map(function (payload) {
    return fetch(OBSERVE_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: JSON.stringify(payload),
      redirect: "follow",
    })
      .then(function (r) {
        return r.ok || r.type === "opaque" || r.redirected;
      })
      .catch(function () {
        remaining.push(payload);
        return false;
      });
  });

  Promise.all(promises).then(function (results) {
    localStorage.setItem("firefly_obs_queue", JSON.stringify(remaining));
    updateQueueBanner();
    var synced = results.filter(Boolean).length;
    if (synced > 0) {
      showStatus("success", "✓ Synced " + synced + " observation(s).");
    }
    if (remaining.length > 0) {
      showStatus(
        "offline",
        remaining.length + " observation(s) still pending."
      );
    }
  });
}

function updateQueueBanner() {
  var banner = document.getElementById("queue-banner");
  if (!banner) return;

  var queue = JSON.parse(localStorage.getItem("firefly_obs_queue") || "[]");
  if (queue.length > 0) {
    banner.style.display = "flex";
    banner.querySelector(".queue-count").textContent =
      queue.length + " pending observation(s)";
  } else {
    banner.style.display = "none";
  }
}

// Auto-sync when coming back online
window.addEventListener("online", function () {
  setTimeout(syncPendingQueue, 1000);
});

// Check queue on page load
document.addEventListener("DOMContentLoaded", updateQueueBanner);

// ─── UI HELPERS ──────────────────────────────────────────────

function showStatus(type, message) {
  var statusDiv = document.getElementById("obs-status");
  if (!statusDiv) return;

  statusDiv.className = "obs-status obs-status-" + type;
  statusDiv.textContent = message;
  statusDiv.style.display = "block";

  // Auto-hide success messages after 5 seconds
  if (type === "success") {
    setTimeout(function () {
      statusDiv.style.display = "none";
    }, 5000);
  }
}

function disableSubmitButtons(disabled) {
  var buttons = document.querySelectorAll(".obs-submit-btn");
  buttons.forEach(function (btn) {
    btn.disabled = disabled;
    btn.style.opacity = disabled ? "0.5" : "1";
  });
}

function resetForm(mode) {
  if (mode === "quick") {
    var species = document.getElementById("quick-species");
    var count = document.getElementById("quick-count");
    var condition = document.getElementById("quick-condition");
    var notes = document.getElementById("quick-notes");
    if (species) species.value = "";
    if (count) count.value = "";
    if (condition) condition.value = "alive";
    if (notes) notes.value = "";
    var infoDiv = document.getElementById("quick-plant-info");
    if (infoDiv) infoDiv.innerHTML = "";
  } else if (mode === "inventory") {
    // Full inventory: clear all inputs
    var inputs = document.querySelectorAll(
      ".inv-count-input, .inv-note-input"
    );
    inputs.forEach(function (input) {
      input.value = "";
    });
    var conditions = document.querySelectorAll(".inv-condition");
    conditions.forEach(function (sel) {
      sel.value = "alive";
    });
  } else if (mode === "comment") {
    var commentNotes = document.getElementById("comment-notes");
    if (commentNotes) commentNotes.value = "";
  } else if (mode === "new_plant") {
    hideAddPlantPanel();
  }

  // Clear section notes (for modes that have them)
  var sectionNotes = document.getElementById("section-notes-" + mode);
  if (sectionNotes) sectionNotes.value = "";

  // Clear photo previews
  var previews = document.querySelectorAll(".obs-photo-preview");
  previews.forEach(function (p) {
    p.remove();
  });
}

function generateUUID() {
  // Simple UUID v4 generator
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0;
    var v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ─── PLANTNET IDENTIFICATION ─────────────────────────────────
//
// Lets a worker take a photo of an unknown plant, send it to the PlantNet
// public API, and pick from the top matches to pre-fill the new-plant
// search box. PLANTNET_API_KEY is injected at build time via
// generate_site.py (from the PLANTNET_API_KEY env var). If the key is
// empty the button stays hidden — no partial UX, no broken calls.
//
// Design: claude-docs/photo-pipeline-and-plant-id-design.md (Step 4).

function initPlantNetIdentify() {
  if (typeof PLANTNET_API_KEY === "undefined" || !PLANTNET_API_KEY) {
    return; // No key → no button.
  }
  var section = document.getElementById("plantnet-section");
  var input = document.getElementById("plantnet-photo-input");
  if (!section || !input) return;

  section.style.display = "";
  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;
    identifyPlantFromFile(file);
    input.value = ""; // allow re-capture of the same plant
  });
}

function identifyPlantFromFile(file) {
  var results = document.getElementById("plantnet-results");
  if (!results) return;

  results.innerHTML =
    '<div class="plantnet-status">Identifying plant — please wait…</div>';

  // Resize to 800px (PlantNet's sweet spot) before upload — keeps the
  // request small over the slow farm connection.
  compressImage(file, 800, 0.8, function (dataUrl) {
    var blob = dataUrlToBlob(dataUrl);
    var formData = new FormData();
    formData.append("images", blob, "observation.jpg");
    formData.append("organs", "auto");

    fetch(
      "https://my-api.plantnet.org/v2/identify/all?api-key=" +
        encodeURIComponent(PLANTNET_API_KEY) +
        "&lang=en&nb-results=3",
      { method: "POST", body: formData }
    )
      .then(function (response) {
        if (!response.ok) {
          return response.text().then(function (txt) {
            throw new Error("PlantNet HTTP " + response.status + ": " + txt);
          });
        }
        return response.json();
      })
      .then(renderPlantNetResults)
      .catch(function (err) {
        console.error("PlantNet identify failed:", err);
        results.innerHTML =
          '<div class="plantnet-status">Identification failed. Check connection and try again.</div>';
      });
  });
}

function dataUrlToBlob(dataUrl) {
  var parts = dataUrl.split(",");
  var mime = (parts[0].match(/:(.*?);/) || [null, "image/jpeg"])[1];
  var binary = atob(parts[1]);
  var len = binary.length;
  var buf = new Uint8Array(len);
  for (var i = 0; i < len; i++) buf[i] = binary.charCodeAt(i);
  return new Blob([buf], { type: mime });
}

function renderPlantNetResults(payload) {
  var results = document.getElementById("plantnet-results");
  if (!results) return;

  var candidates = (payload && payload.results) || [];
  if (candidates.length === 0) {
    results.innerHTML =
      '<div class="plantnet-status">No matches. Try another angle or describe it in notes.</div>';
    return;
  }

  var html = "";
  for (var i = 0; i < Math.min(3, candidates.length); i++) {
    var match = candidates[i];
    var species = (match.species && match.species.scientificNameWithoutAuthor) || "Unknown";
    var common =
      (match.species && match.species.commonNames && match.species.commonNames[0]) || "";
    var score = Math.round((match.score || 0) * 100);

    var farmMatch = findFarmosNameByBotanical(species);
    var displayName = farmMatch || common || species;

    var imgUrl = "";
    if (match.images && match.images.length > 0 && match.images[0].url) {
      imgUrl = match.images[0].url.s || match.images[0].url.m || "";
    }
    var imgTag = imgUrl
      ? '<img src="' + escapeHtml(imgUrl) + '" alt="" loading="lazy">'
      : "";

    html +=
      '<div class="plantnet-match" onclick="applyPlantNetMatch(this)"' +
      ' data-farmos-name="' + escapeHtml(farmMatch || "") + '"' +
      ' data-display="' + escapeHtml(displayName) + '"' +
      ' data-botanical="' + escapeHtml(species) + '">' +
      imgTag +
      '<div class="plantnet-match-text">' +
      '<div class="plantnet-species">' + escapeHtml(displayName) + "</div>" +
      '<div class="plantnet-botanical">' + escapeHtml(species) + "</div>" +
      "</div>" +
      '<div class="plantnet-confidence">' + score + "%</div>" +
      "</div>";
  }

  if (candidates.every(function (c) { return !findFarmosNameByBotanical((c.species || {}).scientificNameWithoutAuthor || ""); })) {
    html +=
      '<div class="plantnet-status">No farm match — species may need to be added to the taxonomy.</div>';
  }
  results.innerHTML = html;
}

function findFarmosNameByBotanical(botanical) {
  if (!botanical || typeof PLANT_TYPES_DATA === "undefined") return "";
  var target = botanical.trim().toLowerCase();
  for (var i = 0; i < PLANT_TYPES_DATA.length; i++) {
    var entry = PLANT_TYPES_DATA[i];
    var bot = (entry.botanical || "").trim().toLowerCase();
    if (bot && (bot === target || target.indexOf(bot) === 0 || bot.indexOf(target) === 0)) {
      return entry.species;
    }
  }
  return "";
}

function applyPlantNetMatch(el) {
  var farmosName = el.dataset.farmosName;
  var displayName = el.dataset.display || farmosName;
  var searchInput = document.getElementById("plant-search");
  if (!searchInput) return;

  if (farmosName) {
    // Known farm species — drive the existing search-and-select flow.
    searchInput.value = farmosName;
    if (typeof filterPlantTypes === "function") {
      filterPlantTypes(farmosName);
    }
    // Auto-select if there's a unique exact match
    var resultsDiv = document.getElementById("plant-search-results");
    if (resultsDiv) {
      var first = resultsDiv.querySelector(".plant-search-result");
      if (first && first.dataset.species === farmosName) {
        selectNewPlant(first);
      }
    }
  } else {
    // Unknown to the farm taxonomy — still seed the search so the worker
    // can confirm it's really new and add it manually.
    searchInput.value = displayName;
    if (typeof filterPlantTypes === "function") {
      filterPlantTypes(displayName);
    }
  }

  // Tidy up the result list so the page doesn't feel cluttered.
  var plantnetResults = document.getElementById("plantnet-results");
  if (plantnetResults) plantnetResults.innerHTML = "";
}
