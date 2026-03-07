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

  // Photo capture handlers
  initPhotoCapture();

  // Show quick mode by default
  switchMode("quick");
}

// ─── MODE SWITCHING ──────────────────────────────────────────

function switchMode(mode) {
  var quickPanel = document.getElementById("mode-quick");
  var inventoryPanel = document.getElementById("mode-inventory");
  var tabs = document.querySelectorAll(".mode-tab");

  tabs.forEach(function (tab) {
    tab.classList.toggle("active", tab.dataset.mode === mode);
  });

  if (quickPanel) quickPanel.style.display = mode === "quick" ? "block" : "none";
  if (inventoryPanel) inventoryPanel.style.display = mode === "inventory" ? "block" : "none";
}

// ─── QUICK OBSERVATION ──────────────────────────────────────

function updateQuickPlantInfo(species) {
  var infoDiv = document.getElementById("quick-plant-info");
  if (!infoDiv || !species) {
    if (infoDiv) infoDiv.innerHTML = "";
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

  // Find plant info from SECTION_DATA
  var plant = null;
  if (typeof SECTION_DATA !== "undefined" && SECTION_DATA.plants) {
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
    previous_count: plant ? (plant.count || 0) : 0,
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
  } else {
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
  }

  // Clear section notes
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
