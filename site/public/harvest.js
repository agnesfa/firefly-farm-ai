/**
 * Firefly Corner Farm — Harvest Log QR Page Logic
 *
 * Vanilla JS — no dependencies. Handles:
 * - Harvester name persistence (localStorage)
 * - Species search with debounced live filtering
 * - Weight input with kg/g toggle
 * - Photo capture with client-side compression
 * - Form submission to Google Apps Script backend
 * - Offline queue with localStorage fallback
 */

// ─── CONFIGURATION ──────────────────────────────────────────

// Endpoint placeholder — set via data-endpoint attribute on body element,
// or replace with actual Apps Script URL once deployed
var HARVEST_ENDPOINT = "";

// ─── INITIALIZATION ──────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  HARVEST_ENDPOINT = document.body.dataset.endpoint || "";

  // Restore harvester name from localStorage
  var savedName = localStorage.getItem("firefly_harvester_name") || "";
  var nameInput = document.getElementById("harvester-name");
  if (nameInput && savedName) {
    nameInput.value = savedName;
  }
  if (nameInput) {
    nameInput.addEventListener("change", function () {
      localStorage.setItem("firefly_harvester_name", this.value.trim());
    });
  }

  // Set current date/time
  var dtInput = document.getElementById("harvest-datetime");
  if (dtInput) {
    var now = new Date();
    var offset = now.getTimezoneOffset();
    var local = new Date(now.getTime() - offset * 60000);
    dtInput.value = local.toISOString().slice(0, 16);
  }

  // Species search with debounce
  var searchInput = document.getElementById("species-search");
  if (searchInput) {
    var debounceTimer = null;
    searchInput.addEventListener("input", function () {
      var q = this.value.trim();
      clearTimeout(debounceTimer);
      if (q.length < 2) {
        hideSearchResults();
        return;
      }
      debounceTimer = setTimeout(function () {
        filterSpecies(q);
      }, 200);
    });
    // Close results on blur (with delay for click to register)
    searchInput.addEventListener("blur", function () {
      setTimeout(hideSearchResults, 200);
    });
  }

  // Unit toggle buttons
  var unitBtns = document.querySelectorAll(".unit-btn");
  unitBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      selectUnit(this);
    });
  });

  // Photo capture
  initPhotoCapture();

  // Submit button
  var submitBtn = document.getElementById("harvest-submit");
  if (submitBtn) {
    submitBtn.addEventListener("click", function (e) {
      e.preventDefault();
      submitHarvest();
    });
  }

  // "Record another" button
  var anotherBtn = document.getElementById("harvest-another");
  if (anotherBtn) {
    anotherBtn.addEventListener("click", function (e) {
      e.preventDefault();
      resetForAnother();
    });
  }

  // Check offline queue
  updateQueueBanner();
});

// ─── SPECIES SEARCH ──────────────────────────────────────────

function filterSpecies(query) {
  var resultsDiv = document.getElementById("species-results");
  if (!resultsDiv) return;

  query = query.toLowerCase();

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
      '<div class="species-result" style="color:#9ca3af;cursor:default">No matches found</div>';
    resultsDiv.style.display = "block";
    return;
  }

  var html = "";
  for (var j = 0; j < matches.length; j++) {
    var m = matches[j];
    var escapedSpecies = escHtml(m.species);
    var escapedBotanical = escHtml(m.botanical || "");
    html +=
      '<div class="species-result" data-species="' + escapedSpecies +
      '" onclick="selectSpecies(this)">' +
      '<div class="species-result-name">' + escapedSpecies + '</div>' +
      '<div class="species-result-botanical">' + escapedBotanical + '</div>' +
      '</div>';
  }

  resultsDiv.innerHTML = html;
  resultsDiv.style.display = "block";
}

function selectSpecies(el) {
  var species = el.dataset.species;
  var searchInput = document.getElementById("species-search");
  if (searchInput) {
    searchInput.value = species;
    searchInput.dataset.selected = species;
  }
  hideSearchResults();

  // Focus weight input
  var weightInput = document.getElementById("harvest-weight");
  if (weightInput) weightInput.focus();
}

function hideSearchResults() {
  var resultsDiv = document.getElementById("species-results");
  if (resultsDiv) resultsDiv.style.display = "none";
}

// ─── UNIT TOGGLE ──────────────────────────────────────────────

function selectUnit(btn) {
  var siblings = btn.parentElement.querySelectorAll(".unit-btn");
  for (var i = 0; i < siblings.length; i++) {
    siblings[i].classList.remove("active");
  }
  btn.classList.add("active");
}

function getSelectedUnit() {
  var activeBtn = document.querySelector(".unit-btn.active");
  return activeBtn ? activeBtn.dataset.unit : "g";
}

// ─── PHOTO CAPTURE ───────────────────────────────────────────

function initPhotoCapture() {
  var photoInput = document.getElementById("harvest-photo-input");
  if (photoInput) {
    photoInput.addEventListener("change", function (e) {
      handlePhotoCapture(e.target);
    });
  }
}

function handlePhotoCapture(input) {
  var file = input.files && input.files[0];
  if (!file) return;

  var previewContainer = document.getElementById("harvest-photo-previews");
  if (!previewContainer) return;

  compressImage(file, 1200, 0.7, function (dataUrl) {
    // Only allow one photo — clear existing
    previewContainer.innerHTML = "";

    var previewDiv = document.createElement("div");
    previewDiv.className = "obs-photo-preview";
    previewDiv.innerHTML =
      '<img src="' + dataUrl + '" alt="Photo preview">' +
      '<button class="obs-photo-remove" onclick="removeHarvestPhoto()" aria-label="Remove photo">&#10005;</button>';
    previewDiv.dataset.base64 = dataUrl;
    previewContainer.appendChild(previewDiv);

    // Reset input so the same file can be re-selected
    input.value = "";
  });
}

function removeHarvestPhoto() {
  var previewContainer = document.getElementById("harvest-photo-previews");
  if (previewContainer) previewContainer.innerHTML = "";
}

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

function getPhotoBase64() {
  var preview = document.querySelector("#harvest-photo-previews .obs-photo-preview");
  return preview ? preview.dataset.base64 : null;
}

// ─── FORM SUBMISSION ─────────────────────────────────────────

function submitHarvest() {
  // Validate harvester name
  var nameInput = document.getElementById("harvester-name");
  if (!nameInput || !nameInput.value.trim()) {
    showStatus("error", "Please enter your name.");
    nameInput && nameInput.focus();
    return;
  }

  // Validate species
  var searchInput = document.getElementById("species-search");
  var species = searchInput ? searchInput.value.trim() : "";
  if (!species) {
    showStatus("error", "Please select a species.");
    searchInput && searchInput.focus();
    return;
  }

  // Validate weight
  var weightInput = document.getElementById("harvest-weight");
  var weightVal = weightInput ? parseFloat(weightInput.value) : 0;
  if (!weightVal || weightVal <= 0) {
    showStatus("error", "Please enter the harvest weight.");
    weightInput && weightInput.focus();
    return;
  }

  // Convert to grams if kg
  var unit = getSelectedUnit();
  var weightGrams = unit === "kg" ? Math.round(weightVal * 1000) : Math.round(weightVal);

  // Get location
  var locationSelect = document.getElementById("harvest-location");
  var location = locationSelect ? locationSelect.value : "";
  if (!location) {
    showStatus("error", "Please select the harvest location.");
    locationSelect && locationSelect.focus();
    return;
  }

  // Get datetime
  var dtInput = document.getElementById("harvest-datetime");
  var timestamp = dtInput ? dtInput.value : new Date().toISOString().slice(0, 16);

  // Get notes
  var notesInput = document.getElementById("harvest-notes");
  var notes = notesInput ? notesInput.value.trim() : "";

  // Get photo
  var photo = getPhotoBase64();

  // Save harvester name
  localStorage.setItem("firefly_harvester_name", nameInput.value.trim());

  // Build payload
  var payload = {
    action: "harvest",
    submission_id: generateUUID(),
    harvester: nameInput.value.trim(),
    timestamp: timestamp,
    species: species,
    weight_grams: weightGrams,
    location: location,
    notes: notes,
    photo: photo
  };

  // Check endpoint
  if (!HARVEST_ENDPOINT) {
    showStatus("error", "Harvest endpoint not configured. Contact Agnes.");
    return;
  }

  showStatus("sending", "Recording harvest...");
  disableSubmit(true);

  // POST to Google Apps Script (text/plain to avoid CORS preflight)
  fetch(HARVEST_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: JSON.stringify(payload),
    redirect: "follow"
  })
    .then(function (response) {
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
        result = { success: true };
      }

      if (result.success) {
        var displayWeight = weightGrams >= 1000
          ? (weightGrams / 1000).toFixed(1) + "kg"
          : weightGrams + "g";
        showStatus(
          "success",
          "Recorded: " + displayWeight + " " + species + " from " + location
        );
        showSuccessState();
      } else {
        showStatus("error", "Error: " + (result.error || "Unknown error"));
      }
    })
    .catch(function (err) {
      if (!navigator.onLine) {
        saveToLocalQueue(payload);
        showStatus(
          "offline",
          "Saved locally — will sync when back online."
        );
        showSuccessState();
      } else {
        showStatus("error", "Failed to send: " + err.message + ". Try again.");
      }
    })
    .finally(function () {
      disableSubmit(false);
    });
}

// ─── SUCCESS STATE ───────────────────────────────────────────

function showSuccessState() {
  var formSection = document.getElementById("harvest-form");
  var successSection = document.getElementById("harvest-success");
  if (formSection) formSection.style.display = "none";
  if (successSection) successSection.style.display = "block";
}

function resetForAnother() {
  var formSection = document.getElementById("harvest-form");
  var successSection = document.getElementById("harvest-success");
  if (formSection) formSection.style.display = "block";
  if (successSection) successSection.style.display = "none";

  // Clear form fields except harvester name
  var searchInput = document.getElementById("species-search");
  if (searchInput) {
    searchInput.value = "";
    delete searchInput.dataset.selected;
  }

  var weightInput = document.getElementById("harvest-weight");
  if (weightInput) weightInput.value = "";

  var locationSelect = document.getElementById("harvest-location");
  if (locationSelect) locationSelect.value = "";

  var notesInput = document.getElementById("harvest-notes");
  if (notesInput) notesInput.value = "";

  removeHarvestPhoto();

  // Reset datetime to now
  var dtInput = document.getElementById("harvest-datetime");
  if (dtInput) {
    var now = new Date();
    var offset = now.getTimezoneOffset();
    var local = new Date(now.getTime() - offset * 60000);
    dtInput.value = local.toISOString().slice(0, 16);
  }

  // Reset unit toggle to grams
  var gBtn = document.querySelector('.unit-btn[data-unit="g"]');
  var kgBtn = document.querySelector('.unit-btn[data-unit="kg"]');
  if (gBtn) gBtn.classList.add("active");
  if (kgBtn) kgBtn.classList.remove("active");

  // Hide status
  var statusDiv = document.getElementById("harvest-status");
  if (statusDiv) statusDiv.style.display = "none";

  // Focus species search
  if (searchInput) searchInput.focus();
}

// ─── OFFLINE QUEUE ───────────────────────────────────────────

function saveToLocalQueue(payload) {
  try {
    var queue = JSON.parse(localStorage.getItem("firefly_harvest_queue") || "[]");
    // Strip photo from localStorage (too large)
    var lightPayload = JSON.parse(JSON.stringify(payload));
    lightPayload.photo = null;
    lightPayload._offline = true;
    queue.push(lightPayload);
    localStorage.setItem("firefly_harvest_queue", JSON.stringify(queue));
    updateQueueBanner();
  } catch (e) {
    console.error("Failed to save to local queue:", e);
  }
}

function syncPendingQueue() {
  var queue = JSON.parse(localStorage.getItem("firefly_harvest_queue") || "[]");
  if (queue.length === 0) return;

  showStatus("sending", "Syncing " + queue.length + " pending harvest(s)...");

  var remaining = [];
  var promises = queue.map(function (payload) {
    return fetch(HARVEST_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: JSON.stringify(payload),
      redirect: "follow"
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
    localStorage.setItem("firefly_harvest_queue", JSON.stringify(remaining));
    updateQueueBanner();
    var synced = results.filter(Boolean).length;
    if (synced > 0) {
      showStatus("success", "Synced " + synced + " harvest(s).");
    }
    if (remaining.length > 0) {
      showStatus("offline", remaining.length + " harvest(s) still pending.");
    }
  });
}

function updateQueueBanner() {
  var banner = document.getElementById("queue-banner");
  if (!banner) return;

  var queue = JSON.parse(localStorage.getItem("firefly_harvest_queue") || "[]");
  if (queue.length > 0) {
    banner.style.display = "flex";
    banner.querySelector(".queue-count").textContent =
      queue.length + " pending harvest(s)";
  } else {
    banner.style.display = "none";
  }
}

// Auto-sync when coming back online
window.addEventListener("online", function () {
  setTimeout(syncPendingQueue, 1000);
});

// ─── UI HELPERS ──────────────────────────────────────────────

function showStatus(type, message) {
  var statusDiv = document.getElementById("harvest-status");
  if (!statusDiv) return;

  statusDiv.className = "obs-status obs-status-" + type;
  statusDiv.textContent = message;
  statusDiv.style.display = "block";

  if (type === "success") {
    setTimeout(function () {
      // Don't auto-hide — user needs to see the summary
    }, 5000);
  }
}

function disableSubmit(disabled) {
  var btn = document.getElementById("harvest-submit");
  if (btn) {
    btn.disabled = disabled;
    btn.style.opacity = disabled ? "0.5" : "1";
  }
}

function escHtml(str) {
  var div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function generateUUID() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0;
    var v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
