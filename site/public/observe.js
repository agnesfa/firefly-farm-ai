/**
 * Firefly Corner Farm — Field Observation Page Logic (v2)
 *
 * Camera-first, photo-driven observation flow.
 * Two modes: Single Plant (photo → identify → record) and Full Section.
 *
 * Vanilla JS — no dependencies.
 */

// ─── INITIALIZATION ──────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  initObservePage();
});

function initObservePage() {
  // Restore observer name from localStorage
  var savedName = localStorage.getItem("firefly_observer_name") || "";
  var nameInput = document.getElementById("observer-name");
  if (nameInput && savedName) nameInput.value = savedName;
  if (nameInput) {
    nameInput.addEventListener("change", function () {
      localStorage.setItem("firefly_observer_name", this.value.trim());
    });
  }

  // Restore and render any recently-submitted observations for this section
  renderRecentSubmissions();

  // Set current date/time
  var dtInput = document.getElementById("obs-datetime");
  if (dtInput) {
    var now = new Date();
    var offset = now.getTimezoneOffset();
    var local = new Date(now.getTime() - offset * 60000);
    dtInput.value = local.toISOString().slice(0, 16);
  }

  // Mode toggle (2 tabs)
  document.querySelectorAll(".mode-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      switchMode(this.dataset.mode);
    });
  });

  // Camera hero button
  var cameraHero = document.getElementById("camera-hero-btn");
  if (cameraHero) {
    cameraHero.addEventListener("click", function () {
      var input = document.getElementById("camera-hero-input");
      if (input) input.click();
    });
  }
  var cameraInput = document.getElementById("camera-hero-input");
  if (cameraInput) {
    cameraInput.addEventListener("change", function () {
      handleCameraHeroCapture(this);
    });
  }

  // Visual plant picker
  document.querySelectorAll(".plant-pick-card").forEach(function (card) {
    card.addEventListener("click", function () {
      selectPlantFromPicker(this.dataset.species);
    });
  });

  // Observation type radios
  document.querySelectorAll('input[name="obs-type"]').forEach(function (r) {
    r.addEventListener("change", updateObsTypeUI);
  });

  // Submit buttons
  var singleSubmit = document.getElementById("single-submit");
  if (singleSubmit) {
    singleSubmit.addEventListener("click", function (e) {
      e.preventDefault();
      submitSinglePlantObservation();
    });
  }

  var sectionSubmit = document.getElementById("section-submit");
  if (sectionSubmit) {
    sectionSubmit.addEventListener("click", function (e) {
      e.preventDefault();
      submitSectionReport();
    });
  }

  // Add New Plant panel
  var plantCloseBtn = document.getElementById("add-plant-close");
  if (plantCloseBtn) {
    plantCloseBtn.addEventListener("click", hideAddPlantPanel);
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

  // Photo capture for observation form (additional photos)
  initPhotoCapture();

  // Multi-photo PlantNet ID
  initMultiPhotoPlantNet();

  // Inventory toggle
  var invToggle = document.getElementById("inventory-toggle");
  if (invToggle) {
    invToggle.addEventListener("click", function () {
      var panel = document.getElementById("inventory-panel");
      if (panel) {
        var open = panel.style.display !== "none";
        panel.style.display = open ? "none" : "block";
        this.querySelector(".inv-toggle-arrow").textContent = open ? "▸" : "▾";
      }
    });
  }

  // Show single plant mode by default
  switchMode("single");

  // Handle URL parameters
  handleUrlParams();
}

// ─── URL PARAMETER HANDLING ──────────────────────────────────

function handleUrlParams() {
  var params = new URLSearchParams(window.location.search);
  var plantParam = params.get("plant");
  var cameraParam = params.get("camera");

  if (plantParam) {
    // Auto-select the plant from picker
    selectPlantFromPicker(plantParam);
  }

  if (cameraParam === "1") {
    // Auto-open camera
    setTimeout(function () {
      var input = document.getElementById("camera-hero-input");
      if (input) input.click();
    }, 300);
  }
}

// ─── MODE SWITCHING ──────────────────────────────────────────

function switchMode(mode) {
  var singlePanel = document.getElementById("mode-single");
  var sectionPanel = document.getElementById("mode-section");
  var tabs = document.querySelectorAll(".mode-tab");

  tabs.forEach(function (tab) {
    tab.classList.toggle("active", tab.dataset.mode === mode);
  });

  if (singlePanel) singlePanel.style.display = mode === "single" ? "block" : "none";
  if (sectionPanel) sectionPanel.style.display = mode === "section" ? "block" : "none";
}

// ─── CAMERA HERO FLOW ────────────────────────────────────────

function handleCameraHeroCapture(input) {
  var file = input.files && input.files[0];
  if (!file) return;

  // Show photo in hero area as preview
  compressImage(file, 1200, 0.7, function (fullDataUrl) {
    // Store full-res for observation attachment
    var heroPreview = document.getElementById("camera-hero-preview");
    if (heroPreview) {
      heroPreview.innerHTML =
        '<img src="' + fullDataUrl + '" alt="Captured photo" class="hero-preview-img">';
      heroPreview.dataset.base64 = fullDataUrl;
      heroPreview.style.display = "block";
    }

    // Hide camera button, show preview area
    var heroBtn = document.getElementById("camera-hero-btn");
    if (heroBtn) heroBtn.style.display = "none";

    // Add to multi-photo strip for PlantNet
    addPhotoToIdStrip(fullDataUrl, "auto");

    // Auto-run PlantNet identification
    if (typeof PLANTNET_API_KEY !== "undefined" && PLANTNET_API_KEY) {
      runPlantNetIdentification();
    } else {
      // No PlantNet — show plant picker directly
      showPlantPickerAfterPhoto();
    }
  });

  input.value = "";
}

function showPlantPickerAfterPhoto() {
  var picker = document.getElementById("plant-picker-section");
  if (picker) picker.style.display = "block";
}

// ─── MULTI-PHOTO PLANTNET ────────────────────────────────────

var plantnetPhotos = []; // [{blob, dataUrl, organ}]

function initMultiPhotoPlantNet() {
  var addMoreBtn = document.getElementById("plantnet-add-more");
  if (addMoreBtn) {
    addMoreBtn.addEventListener("click", function () {
      var input = document.getElementById("plantnet-more-input");
      if (input) input.click();
    });
  }

  var moreInput = document.getElementById("plantnet-more-input");
  if (moreInput) {
    moreInput.addEventListener("change", function () {
      var file = this.files && this.files[0];
      if (!file) return;
      compressImage(file, 1200, 0.7, function (dataUrl) {
        addPhotoToIdStrip(dataUrl, "auto");
        runPlantNetIdentification();
      });
      this.value = "";
    });
  }

  // Organ chip selection
  document.addEventListener("click", function (e) {
    if (e.target.classList.contains("organ-chip")) {
      var strip = e.target.closest(".id-photo-item");
      if (!strip) return;
      var idx = parseInt(strip.dataset.index, 10);
      var organ = e.target.dataset.organ;
      // Toggle active
      strip.querySelectorAll(".organ-chip").forEach(function (c) {
        c.classList.toggle("active", c.dataset.organ === organ);
      });
      if (plantnetPhotos[idx]) {
        plantnetPhotos[idx].organ = organ;
        // Re-run identification with updated organs
        runPlantNetIdentification();
      }
    }
  });
}

function addPhotoToIdStrip(dataUrl, organ) {
  if (plantnetPhotos.length >= 5) return;

  var blob = dataUrlToBlob(dataUrl);
  var idx = plantnetPhotos.length;
  plantnetPhotos.push({ blob: blob, dataUrl: dataUrl, organ: organ });

  var strip = document.getElementById("id-photo-strip");
  if (!strip) return;
  strip.style.display = "flex";

  var item = document.createElement("div");
  item.className = "id-photo-item";
  item.dataset.index = idx;
  item.innerHTML =
    '<img src="' + dataUrl + '" alt="Photo ' + (idx + 1) + '">' +
    '<button class="id-photo-remove" onclick="removeIdPhoto(' + idx + ')">✕</button>' +
    '<div class="organ-chips">' +
    '<span class="organ-chip' + (organ === "auto" ? " active" : "") + '" data-organ="auto">Auto</span>' +
    '<span class="organ-chip' + (organ === "leaf" ? " active" : "") + '" data-organ="leaf">Leaf</span>' +
    '<span class="organ-chip' + (organ === "flower" ? " active" : "") + '" data-organ="flower">Flower</span>' +
    '<span class="organ-chip' + (organ === "fruit" ? " active" : "") + '" data-organ="fruit">Fruit</span>' +
    '<span class="organ-chip' + (organ === "bark" ? " active" : "") + '" data-organ="bark">Bark</span>' +
    '</div>';
  strip.appendChild(item);

  // Show/hide "add more" button
  var addMore = document.getElementById("plantnet-add-more");
  if (addMore) {
    addMore.style.display = plantnetPhotos.length < 5 ? "inline-flex" : "none";
    addMore.textContent = "📷 Add another angle (" + plantnetPhotos.length + "/5)";
  }
}

function removeIdPhoto(idx) {
  plantnetPhotos.splice(idx, 1);
  rebuildIdStrip();
  if (plantnetPhotos.length > 0) {
    runPlantNetIdentification();
  } else {
    // Reset to camera hero
    var heroBtn = document.getElementById("camera-hero-btn");
    var heroPreview = document.getElementById("camera-hero-preview");
    if (heroBtn) heroBtn.style.display = "";
    if (heroPreview) { heroPreview.style.display = "none"; heroPreview.innerHTML = ""; }
    var results = document.getElementById("plantnet-results");
    if (results) results.innerHTML = "";
    var strip = document.getElementById("id-photo-strip");
    if (strip) strip.style.display = "none";
    var addMore = document.getElementById("plantnet-add-more");
    if (addMore) addMore.style.display = "none";
  }
}

function rebuildIdStrip() {
  var strip = document.getElementById("id-photo-strip");
  if (!strip) return;
  strip.innerHTML = "";
  var photos = plantnetPhotos.slice();
  plantnetPhotos = [];
  photos.forEach(function (p) {
    addPhotoToIdStrip(p.dataUrl, p.organ);
  });
}

function runPlantNetIdentification() {
  if (plantnetPhotos.length === 0) return;
  if (typeof PLANTNET_API_KEY === "undefined" || !PLANTNET_API_KEY) return;

  var results = document.getElementById("plantnet-results");
  if (results) {
    results.style.display = "block";
    results.innerHTML = '<div class="plantnet-status">Identifying plant — please wait...</div>';
  }

  // Build FormData with all photos
  var formData = new FormData();
  plantnetPhotos.forEach(function (p) {
    // Compress to 800px for PlantNet
    formData.append("images", p.blob, "photo.jpg");
    formData.append("organs", p.organ);
  });

  fetch(
    "https://my-api.plantnet.org/v2/identify/all?api-key=" +
      encodeURIComponent(PLANTNET_API_KEY) +
      "&lang=en&nb-results=5",
    { method: "POST", body: formData }
  )
    .then(function (response) {
      if (!response.ok) {
        return response.text().then(function (txt) {
          throw new Error("PlantNet HTTP " + response.status);
        });
      }
      return response.json();
    })
    .then(renderPlantNetResults)
    .catch(function (err) {
      console.error("PlantNet failed:", err);
      if (results) {
        results.innerHTML =
          '<div class="plantnet-status">Identification failed. Try again or select a plant manually.</div>';
      }
      showPlantPickerAfterPhoto();
    });
}

// ─── PLANTNET RESULTS (SECTION-CONTEXT) ──────────────────────

function renderPlantNetResults(payload) {
  var results = document.getElementById("plantnet-results");
  if (!results) return;

  var candidates = (payload && payload.results) || [];
  if (candidates.length === 0) {
    results.innerHTML =
      '<div class="plantnet-status">No matches found. Try another angle or select a plant below.</div>';
    showPlantPickerAfterPhoto();
    return;
  }

  var html = "";
  var hasLowConfidence = true;

  for (var i = 0; i < Math.min(5, candidates.length); i++) {
    var match = candidates[i];
    var botanical = (match.species && match.species.scientificNameWithoutAuthor) || "Unknown";
    var common =
      (match.species && match.species.commonNames && match.species.commonNames[0]) || "";
    var score = Math.round((match.score || 0) * 100);

    if (score >= 20) hasLowConfidence = false;

    var farmMatch = findFarmosNameByBotanical(botanical);
    var inSection = farmMatch ? isSpeciesInSection(farmMatch) : false;
    var displayName = farmMatch || common || botanical;

    // Context badge
    var badge = "";
    if (inSection) {
      var sectionPlant = getSectionPlant(farmMatch);
      var countText = sectionPlant ? " (" + (sectionPlant.count || 0) + " plants)" : "";
      badge = '<span class="pn-badge pn-badge-section">In this section' + countText + '</span>';
    } else if (farmMatch) {
      badge = '<span class="pn-badge pn-badge-farm">In farm taxonomy</span>';
    } else {
      badge = '<span class="pn-badge pn-badge-unknown">New to farm</span>';
    }

    var imgUrl = "";
    if (match.images && match.images.length > 0 && match.images[0].url) {
      imgUrl = match.images[0].url.s || match.images[0].url.m || "";
    }
    var imgTag = imgUrl
      ? '<img src="' + escapeHtml(imgUrl) + '" alt="" loading="lazy">'
      : '<div class="pn-no-img">?</div>';

    html +=
      '<div class="plantnet-match" onclick="applyPlantNetMatch(this)"' +
      ' data-farmos-name="' + escapeHtml(farmMatch || "") + '"' +
      ' data-display="' + escapeHtml(displayName) + '"' +
      ' data-botanical="' + escapeHtml(botanical) + '"' +
      ' data-in-section="' + (inSection ? "1" : "0") + '">' +
      imgTag +
      '<div class="plantnet-match-text">' +
      '<div class="plantnet-species">' + escapeHtml(displayName) + "</div>" +
      '<div class="plantnet-botanical">' + escapeHtml(botanical) + "</div>" +
      badge +
      "</div>" +
      '<div class="plantnet-confidence">' + score + "%</div>" +
      "</div>";
  }

  if (hasLowConfidence && plantnetPhotos.length < 5) {
    html +=
      '<div class="plantnet-status">Low confidence — add another photo from a different angle for better results.</div>';
  }

  results.innerHTML = html;
  results.style.display = "block";

  // Always show picker below results
  showPlantPickerAfterPhoto();
}

function isSpeciesInSection(species) {
  if (typeof SECTION_DATA === "undefined" || !SECTION_DATA.plants) return false;
  for (var i = 0; i < SECTION_DATA.plants.length; i++) {
    if (SECTION_DATA.plants[i].species === species) return true;
  }
  return false;
}

function getSectionPlant(species) {
  if (typeof SECTION_DATA === "undefined" || !SECTION_DATA.plants) return null;
  for (var i = 0; i < SECTION_DATA.plants.length; i++) {
    if (SECTION_DATA.plants[i].species === species) return SECTION_DATA.plants[i];
  }
  return null;
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
  var inSection = el.dataset.inSection === "1";

  if (farmosName && inSection) {
    // Existing plant in section — select it directly
    selectPlantFromPicker(farmosName);
  } else if (farmosName) {
    // In taxonomy but not in section — open Add New Plant flow
    showAddPlantPanel();
    var searchInput = document.getElementById("plant-search");
    if (searchInput) {
      searchInput.value = farmosName;
      filterPlantTypes(farmosName);
      // Auto-select first match
      setTimeout(function () {
        var resultsDiv = document.getElementById("plant-search-results");
        if (resultsDiv) {
          var first = resultsDiv.querySelector(".plant-search-result");
          if (first && first.dataset.species === farmosName) {
            selectNewPlant(first);
          }
        }
      }, 50);
    }
  } else {
    // Unknown — open Add New Plant with display name
    showAddPlantPanel();
    var searchInput = document.getElementById("plant-search");
    if (searchInput) {
      searchInput.value = el.dataset.display || el.dataset.botanical || "";
      filterPlantTypes(searchInput.value);
    }
  }
}

// ─── VISUAL PLANT PICKER ─────────────────────────────────────

var selectedPlantSpecies = null;

function selectPlantFromPicker(species) {
  selectedPlantSpecies = species;

  // Handle Unknown
  if (species === "Unknown") {
    showAddPlantPanel();
    return;
  }

  // Highlight selected card
  document.querySelectorAll(".plant-pick-card").forEach(function (card) {
    card.classList.toggle("selected", card.dataset.species === species);
  });

  // Find plant data
  var plant = getSectionPlant(species);
  if (!plant) {
    // May be from PlantNet match — try taxonomy
    selectedPlantSpecies = species;
  }

  // Show observation form
  var form = document.getElementById("single-obs-form");
  if (form) {
    form.style.display = "block";
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Populate form header
  var nameEl = document.getElementById("selected-plant-name");
  var countEl = document.getElementById("selected-plant-count");
  if (nameEl) nameEl.textContent = species;
  var currentCount = plant ? plant.count : null;
  if (countEl) {
    var display = currentCount !== null && currentCount !== undefined ? currentCount : "—";
    countEl.textContent = "Current count: " + display;
  }

  // PREFILL the New count input with the current farmOS count so that
  // if the observer doesn't change it, submission is a no-op on inventory.
  // Workers focused on photos / condition notes no longer accidentally
  // reset counts to zero or to a rough eyeball number.
  var countInput = document.getElementById("single-count");
  if (countInput) {
    if (currentCount !== null && currentCount !== undefined) {
      countInput.value = String(currentCount);
    } else {
      countInput.value = "";
    }
  }
}

// ─── OBSERVATION TYPE ────────────────────────────────────────

function updateObsTypeUI() {
  var selected = document.querySelector('input[name="obs-type"]:checked');
  if (!selected) return;
  var notesInput = document.getElementById("single-notes");
  if (notesInput) {
    var placeholders = {
      observation: "What did you see? (condition, growth, pests...)",
      activity: "What did you do? (watered, pruned, mulched...)",
      todo: "What needs to be done? (needs staking, water, harvest...)"
    };
    notesInput.placeholder = placeholders[selected.value] || "";
  }
}

// ─── SINGLE PLANT SUBMISSION ─────────────────────────────────

function submitSinglePlantObservation() {
  if (!selectedPlantSpecies) {
    showStatus("error", "Please select a plant first.");
    return;
  }

  var plant = getSectionPlant(selectedPlantSpecies);
  // ADR 0008 I11: obs-type radios removed from the UI (2026-04-20).
  // Log type + status are derived from notes text by the importer's
  // classifier. Guard left for backwards compat with cached pages.
  var obsType = document.querySelector('input[name="obs-type"]:checked');
  var count = document.getElementById("single-count");
  var condition = document.getElementById("single-condition");
  var notes = document.getElementById("single-notes");

  var obs = {
    species: selectedPlantSpecies,
    strata: plant ? plant.strata : "",
    previous_count: plant ? (plant.count || 0) : 0,
    condition: condition ? condition.value : "alive",
    notes: notes ? notes.value.trim() : "",
    obs_type: obsType ? obsType.value : "observation",
  };

  if (count && count.value !== "") {
    obs.new_count = parseFloat(count.value);
  }

  submitObservation({
    observations: [obs],
    section_notes: "",
    mode: "quick",
  });
}

// ─── SECTION REPORT SUBMISSION ───────────────────────────────

function submitSectionReport() {
  var sectionNotes = document.getElementById("section-notes");
  var observations = [];

  // Collect inventory changes
  var rows = document.querySelectorAll(".inv-plant-row");
  rows.forEach(function (row) {
    var countInput = row.querySelector(".inv-count-input");
    var noteInput = row.querySelector(".inv-note-input");
    var conditionSelect = row.querySelector(".inv-condition");

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
      if (hasCount) obs.new_count = parseFloat(countInput.value);
      observations.push(obs);
    }
  });

  var notesValue = sectionNotes ? sectionNotes.value.trim() : "";

  if (observations.length === 0 && !notesValue) {
    showStatus("error", "Please add section notes or update at least one plant.");
    return;
  }

  // Determine mode based on content
  var mode = observations.length > 0 ? "inventory" : "comment";

  submitObservation({
    observations: observations,
    section_notes: notesValue,
    mode: mode,
  });
}

// ─── ADD NEW PLANT ───────────────────────────────────────────

function showAddPlantPanel() {
  var panel = document.getElementById("add-plant-panel");
  if (panel) {
    panel.style.display = "block";
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    var searchInput = document.getElementById("plant-search");
    if (searchInput && !searchInput.value) searchInput.focus();
    var fieldsDiv = document.getElementById("new-plant-fields");
    if (fieldsDiv) fieldsDiv.style.display = "none";
  }
}

function hideAddPlantPanel() {
  var panel = document.getElementById("add-plant-panel");
  if (panel) panel.style.display = "none";
  var searchInput = document.getElementById("plant-search");
  if (searchInput) searchInput.value = "";
  var resultsDiv = document.getElementById("plant-search-results");
  if (resultsDiv) { resultsDiv.style.display = "none"; resultsDiv.innerHTML = ""; }
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
    html +=
      '<div class="plant-search-result" data-species="' + escapeHtml(m.species) +
      '" data-strata="' + escapeHtml(m.strata || "") +
      '" data-botanical="' + escapeHtml(m.botanical || "") +
      '" onclick="selectNewPlant(this)">' +
      '<div class="search-species">' + escapeHtml(m.species) + '</div>' +
      '<div class="search-meta">' + escapeHtml(m.botanical || "") +
      (m.strata ? " · " + escapeHtml(m.strata) : "") + '</div>' +
      '</div>';
  }

  resultsDiv.innerHTML = html;
  resultsDiv.style.display = "block";
}

function selectNewPlant(el) {
  var species = el.dataset.species;
  var strata = el.dataset.strata;

  var speciesDisplay = document.getElementById("new-plant-species");
  var strataDisplay = document.getElementById("new-plant-strata");
  if (speciesDisplay) speciesDisplay.textContent = species;
  if (strataDisplay) strataDisplay.textContent = strata || "—";

  var fieldsDiv = document.getElementById("new-plant-fields");
  if (fieldsDiv) {
    fieldsDiv.style.display = "block";
    fieldsDiv.dataset.selectedSpecies = species;
    fieldsDiv.dataset.selectedStrata = strata;
  }

  var resultsDiv = document.getElementById("plant-search-results");
  if (resultsDiv) resultsDiv.style.display = "none";
  var searchInput = document.getElementById("plant-search");
  if (searchInput) searchInput.value = species;
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

// ─── SUBMISSION ──────────────────────────────────────────────

function submitObservation(formData) {
  var nameInput = document.getElementById("observer-name");
  var dtInput = document.getElementById("obs-datetime");

  if (!nameInput || !nameInput.value.trim()) {
    showStatus("error", "Please enter your name.");
    if (nameInput) nameInput.focus();
    return;
  }

  localStorage.setItem("firefly_observer_name", nameInput.value.trim());

  var subId = generateUUID();
  var payload = {
    version: "1",
    submission_id: subId,
    section_id: typeof SECTION_DATA !== "undefined" ? SECTION_DATA.id : "",
    observer: nameInput.value.trim(),
    timestamp: dtInput ? new Date(dtInput.value).toISOString() : new Date().toISOString(),
    mode: formData.mode,
    observations: formData.observations,
    section_notes: formData.section_notes,
    media: collectMediaData(subId),
  };

  if (typeof OBSERVE_ENDPOINT === "undefined" || !OBSERVE_ENDPOINT) {
    showStatus("error", "Observation endpoint not configured. Contact Agnes.");
    return;
  }

  showStatus("sending", "Sending observation...");
  disableSubmitButtons(true);

  fetch(OBSERVE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: JSON.stringify(payload),
    redirect: "follow",
  })
    .then(function (response) {
      if (response.ok || response.type === "opaque" || response.redirected) {
        return response.text().catch(function () { return '{"success": true}'; });
      }
      throw new Error("Server returned " + response.status);
    })
    .then(function (text) {
      var result;
      try { result = JSON.parse(text); } catch (e) { result = { success: true }; }

      if (result.success) {
        showStatus("success",
          "Observation saved!" +
          (result.duplicate ? " (already recorded)" : "") +
          (result.message ? " " + result.message : "")
        );
        storeRecentSubmission(payload, "pending");
        renderRecentSubmissions();
        resetForm(formData.mode);
      } else {
        showStatus("error", "Error: " + (result.error || "Unknown error"));
      }
    })
    .catch(function (err) {
      if (!navigator.onLine) {
        saveToLocalQueue(payload);
        showStatus("offline", "Saved locally — will sync when back online.");
        storeRecentSubmission(payload, "offline");
        renderRecentSubmissions();
        resetForm(formData.mode);
      } else {
        showStatus("error", "Failed to send: " + err.message);
      }
    })
    .finally(function () {
      disableSubmitButtons(false);
    });
}

// ─── PHOTO CAPTURE (additional photos on form) ───────────────

function initPhotoCapture() {
  document.querySelectorAll(".obs-photo-input").forEach(function (input) {
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

  compressImage(file, 1200, 0.7, function (dataUrl) {
    var previewDiv = document.createElement("div");
    previewDiv.className = "obs-photo-preview";
    previewDiv.innerHTML =
      '<img src="' + dataUrl + '" alt="Photo preview">' +
      '<button class="obs-photo-remove" onclick="this.parentElement.remove()" aria-label="Remove photo">✕</button>';
    previewDiv.dataset.base64 = dataUrl;
    previewDiv.dataset.target = input.dataset.target || "section";
    previewContainer.appendChild(previewDiv);
    input.value = "";
  });
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
        if (w > h) { h = Math.round((h * maxDim) / w); w = maxDim; }
        else { w = Math.round((w * maxDim) / h); h = maxDim; }
      }
      canvas.width = w;
      canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      callback(canvas.toDataURL("image/jpeg", quality));
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function collectMediaData(submissionId) {
  var media = [];
  var counter = 1;
  var sectionId = typeof SECTION_DATA !== "undefined" ? SECTION_DATA.id : "unknown";
  // Prefix every filename with the first 8 chars of the submission ID so
  // Observations.gs handleGetMedia can filter files by submission when the
  // Drive folder groups multiple submissions. Without this, get_media
  // returns the entire date+section folder (bug discovered April 15 2026,
  // Leah's walk: 180 photos cross-contaminated across 15 logs). ADR 0005.
  var prefix = submissionId ? submissionId.substring(0, 8) : "00000000";

  // Collect hero photo
  var heroPreview = document.getElementById("camera-hero-preview");
  if (heroPreview && heroPreview.dataset.base64) {
    media.push({
      type: "photo",
      target: "plant",
      filename: prefix + "_" + sectionId + "_plant_" + String(counter).padStart(3, "0") + ".jpg",
      data: heroPreview.dataset.base64,
    });
    counter++;
  }

  // Collect additional PlantNet identification angles as evidence
  // photos on the log (ADR 0008 Step 3 / I9 UX clarity). The hero
  // above is plantnetPhotos[0]; angles 2..N are added here. Tagged
  // target=plant so they attach to the plant log on import. Skip
  // the first entry since it's already covered by the hero preview
  // read above.
  if (typeof plantnetPhotos !== "undefined" && plantnetPhotos.length > 1) {
    for (var pi = 1; pi < plantnetPhotos.length; pi++) {
      var p = plantnetPhotos[pi];
      if (!p || !p.dataUrl) continue;
      media.push({
        type: "photo",
        target: "plant",
        filename: prefix + "_" + sectionId + "_plant_" + String(counter).padStart(3, "0") + ".jpg",
        data: p.dataUrl,
      });
      counter++;
    }
  }

  // Collect additional photos
  document.querySelectorAll(".obs-photo-preview").forEach(function (preview) {
    if (preview.dataset.base64) {
      media.push({
        type: "photo",
        target: preview.dataset.target || "section",
        filename: prefix + "_" + sectionId + "_" + (preview.dataset.target || "section") + "_" + String(counter).padStart(3, "0") + ".jpg",
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
      .then(function (r) { return r.ok || r.type === "opaque" || r.redirected; })
      .catch(function () { remaining.push(payload); return false; });
  });

  Promise.all(promises).then(function (results) {
    localStorage.setItem("firefly_obs_queue", JSON.stringify(remaining));
    updateQueueBanner();
    var synced = results.filter(Boolean).length;
    if (synced > 0) showStatus("success", "Synced " + synced + " observation(s).");
    if (remaining.length > 0) showStatus("offline", remaining.length + " still pending.");
  });
}

function updateQueueBanner() {
  var banner = document.getElementById("queue-banner");
  if (!banner) return;
  var queue = JSON.parse(localStorage.getItem("firefly_obs_queue") || "[]");
  if (queue.length > 0) {
    banner.style.display = "flex";
    banner.querySelector(".queue-count").textContent = queue.length + " pending observation(s)";
  } else {
    banner.style.display = "none";
  }
}

window.addEventListener("online", function () { setTimeout(syncPendingQueue, 1000); });
document.addEventListener("DOMContentLoaded", updateQueueBanner);

// ─── UI HELPERS ──────────────────────────────────────────────

function showStatus(type, message) {
  var statusDiv = document.getElementById("obs-status");
  if (!statusDiv) return;
  statusDiv.className = "obs-status obs-status-" + type;
  statusDiv.textContent = message;
  statusDiv.style.display = "block";
  if (type === "success") {
    setTimeout(function () { statusDiv.style.display = "none"; }, 8000);
  }
}

function disableSubmitButtons(disabled) {
  document.querySelectorAll(".obs-submit-btn").forEach(function (btn) {
    btn.disabled = disabled;
    btn.style.opacity = disabled ? "0.5" : "1";
  });
}

function resetForm(mode) {
  if (mode === "quick" || mode === "new_plant") {
    // Reset single plant form
    selectedPlantSpecies = null;
    var form = document.getElementById("single-obs-form");
    if (form) form.style.display = "none";

    document.querySelectorAll(".plant-pick-card").forEach(function (c) {
      c.classList.remove("selected");
    });

    var count = document.getElementById("single-count");
    var condition = document.getElementById("single-condition");
    var notes = document.getElementById("single-notes");
    if (count) count.value = "";
    if (condition) condition.value = "alive";
    if (notes) notes.value = "";

    // Reset camera hero — clear dataset.base64 too (not just innerHTML).
    // Without this, the old photo leaks into the next submission via
    // collectMediaData which reads heroPreview.dataset.base64.
    var heroBtn = document.getElementById("camera-hero-btn");
    var heroPreview = document.getElementById("camera-hero-preview");
    if (heroBtn) heroBtn.style.display = "";
    if (heroPreview) { heroPreview.style.display = "none"; heroPreview.innerHTML = ""; delete heroPreview.dataset.base64; }

    // Reset PlantNet
    plantnetPhotos = [];
    var strip = document.getElementById("id-photo-strip");
    if (strip) { strip.innerHTML = ""; strip.style.display = "none"; }
    var pnResults = document.getElementById("plantnet-results");
    if (pnResults) { pnResults.innerHTML = ""; pnResults.style.display = "none"; }
    var addMore = document.getElementById("plantnet-add-more");
    if (addMore) addMore.style.display = "none";

    // Reset radios
    var obsRadio = document.getElementById("obs-type-observation");
    if (obsRadio) obsRadio.checked = true;
    updateObsTypeUI();

    hideAddPlantPanel();
  } else if (mode === "inventory" || mode === "comment") {
    var inputs = document.querySelectorAll(".inv-count-input, .inv-note-input");
    inputs.forEach(function (i) { i.value = ""; });
    var conditions = document.querySelectorAll(".inv-condition");
    conditions.forEach(function (s) { s.value = "alive"; });
    var sectionNotes = document.getElementById("section-notes");
    if (sectionNotes) sectionNotes.value = "";
  }

  // Clear additional photo previews
  document.querySelectorAll(".obs-photo-preview").forEach(function (p) { p.remove(); });
}

function generateUUID() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0;
    var v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function escapeHtml(text) {
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ─── RECENT SUBMISSIONS (pending-review card) ──────────────────
//
// After a worker submits an observation, show a "Pending review" card with
// what they just sent. Persists in localStorage per section_id so the card
// survives page reload — the worker sees their submission is recorded even
// if farmOS hasn't processed it yet. Entries age out after 24 hours and
// are manually dismissible.

var RECENT_SUBMISSIONS_KEY = "firefly_recent_submissions";
var RECENT_SUBMISSIONS_MAX_AGE_MS = 24 * 60 * 60 * 1000;  // 24 hours
var RECENT_SUBMISSIONS_MAX_PER_SECTION = 10;

function getSectionId() {
  return (typeof SECTION_DATA !== "undefined" && SECTION_DATA.id) || "unknown";
}

function loadRecentSubmissions() {
  try {
    var raw = localStorage.getItem(RECENT_SUBMISSIONS_KEY);
    if (!raw) return {};
    var parsed = JSON.parse(raw);
    // Prune expired entries section-by-section
    var cutoff = Date.now() - RECENT_SUBMISSIONS_MAX_AGE_MS;
    for (var sid in parsed) {
      if (!parsed.hasOwnProperty(sid)) continue;
      parsed[sid] = (parsed[sid] || []).filter(function (s) {
        return s.stored_at && s.stored_at > cutoff;
      });
      if (parsed[sid].length === 0) delete parsed[sid];
    }
    return parsed;
  } catch (e) {
    return {};
  }
}

function saveRecentSubmissions(data) {
  try {
    localStorage.setItem(RECENT_SUBMISSIONS_KEY, JSON.stringify(data));
  } catch (e) { /* quota — drop silently */ }
}

function storeRecentSubmission(payload, state) {
  var sid = payload.section_id || getSectionId();
  var data = loadRecentSubmissions();
  if (!data[sid]) data[sid] = [];

  // Keep only the serializable bits + a small thumbnail preview per media
  var mediaPreviews = [];
  (payload.media || []).forEach(function (m) {
    if (m && m.data) {
      mediaPreviews.push({
        filename: m.filename || "photo.jpg",
        data: m.data,  // full base64 (small, and we cap total entries)
        target: m.target || "section",
      });
    }
  });

  var entry = {
    submission_id: payload.submission_id,
    stored_at: Date.now(),
    timestamp: payload.timestamp,
    observer: payload.observer,
    mode: payload.mode,
    state: state || "pending",
    observations: (payload.observations || []).map(function (o) {
      return {
        species: o.species,
        new_count: o.new_count,
        previous_count: o.previous_count,
        condition: o.condition,
        notes: o.notes,
        obs_type: o.obs_type,
        mode: o.mode,
      };
    }),
    section_notes: payload.section_notes || "",
    media: mediaPreviews,
  };

  data[sid].unshift(entry);
  // Cap per-section to prevent runaway storage
  data[sid] = data[sid].slice(0, RECENT_SUBMISSIONS_MAX_PER_SECTION);
  saveRecentSubmissions(data);
}

function dismissRecentSubmission(submissionId) {
  var sid = getSectionId();
  var data = loadRecentSubmissions();
  if (!data[sid]) return;
  data[sid] = data[sid].filter(function (e) { return e.submission_id !== submissionId; });
  if (data[sid].length === 0) delete data[sid];
  saveRecentSubmissions(data);
  renderRecentSubmissions();
}

function renderRecentSubmissions() {
  var sid = getSectionId();
  var data = loadRecentSubmissions();
  var entries = data[sid] || [];

  var container = document.getElementById("recent-submissions");
  if (!container) {
    // Insert at top of page, just after the section header
    var page = document.querySelector(".page");
    if (!page) return;
    container = document.createElement("div");
    container.id = "recent-submissions";
    container.className = "recent-submissions";
    // Place after the queue banner if present, else right after section header
    var queueBanner = document.getElementById("queue-banner");
    var afterEl = queueBanner || document.querySelector(".section-header");
    if (afterEl && afterEl.parentNode) {
      afterEl.parentNode.insertBefore(container, afterEl.nextSibling);
    } else {
      page.insertBefore(container, page.firstChild);
    }
  }

  if (entries.length === 0) {
    container.innerHTML = "";
    container.style.display = "none";
    return;
  }

  var header = '<div class="recent-header">' +
    '<span class="recent-icon">⏳</span>' +
    '<span class="recent-title">Your recent submissions — pending review</span>' +
    '</div>' +
    '<div class="recent-intro">These observations have been saved. Agnes or Claire ' +
    'will review and sync them into farmOS shortly. You can keep observing.</div>';

  var cards = entries.map(function (e) {
    var when = new Date(e.timestamp || e.stored_at).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
    });
    var stateBadge = e.state === "offline"
      ? '<span class="recent-state-badge offline">📴 offline — will sync</span>'
      : '<span class="recent-state-badge pending">⏳ pending review</span>';

    var thumbs = "";
    if (e.media && e.media.length > 0) {
      thumbs = '<div class="recent-thumbs">' +
        e.media.slice(0, 4).map(function (m) {
          return '<div class="recent-thumb"><img src="' + escapeHtml(m.data) + '" alt=""></div>';
        }).join("") +
        (e.media.length > 4 ? '<div class="recent-thumb more">+' + (e.media.length - 4) + '</div>' : '') +
        '</div>';
    }

    var rows = (e.observations || []).map(function (o) {
      var kind = o.obs_type === "activity" ? "🔧"
               : o.obs_type === "todo" ? "📌"
               : o.mode === "new_plant" ? "🌱 new"
               : "👁";
      var countChange = "";
      if (o.new_count !== null && o.new_count !== undefined) {
        if (o.previous_count !== null && o.previous_count !== undefined &&
            Number(o.new_count) !== Number(o.previous_count)) {
          countChange = ' · <span class="recent-count-change">' + o.previous_count + ' → ' + o.new_count + '</span>';
        } else {
          countChange = ' · <span class="recent-count">' + o.new_count + '</span>';
        }
      }
      var noteHtml = o.notes ? '<div class="recent-note">' + escapeHtml(o.notes) + '</div>' : '';
      return '<div class="recent-obs-row">' +
        '<span class="recent-kind">' + kind + '</span> ' +
        '<strong>' + escapeHtml(o.species || "—") + '</strong>' +
        countChange +
        noteHtml +
        '</div>';
    }).join("");

    if (e.section_notes) {
      rows += '<div class="recent-obs-row"><span class="recent-kind">📋</span> <strong>Section notes:</strong> <div class="recent-note">' +
        escapeHtml(e.section_notes) + '</div></div>';
    }

    return '<div class="recent-card">' +
      '<div class="recent-card-header">' +
        '<span class="recent-when">' + when + '</span>' +
        stateBadge +
        '<button class="recent-dismiss" onclick="dismissRecentSubmission(\'' + e.submission_id + '\')" title="Dismiss">✕</button>' +
      '</div>' +
      thumbs +
      '<div class="recent-card-body">' + rows + '</div>' +
      '</div>';
  }).join("");

  container.innerHTML = header + cards;
  container.style.display = "block";
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
