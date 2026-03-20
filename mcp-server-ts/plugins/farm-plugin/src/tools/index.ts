// Barrel export — all 29 farm tools (28 ported + hello)
import { helloTool } from './hello.js';

// READ TOOLS (7)
import { queryPlantsTool } from './query-plants.js';
import { querySectionsTool } from './query-sections.js';
import { getPlantDetailTool } from './get-plant-detail.js';
import { queryLogsTool } from './query-logs.js';
import { getInventoryTool } from './get-inventory.js';
import { searchPlantTypesTool } from './search-plant-types.js';
import { getAllPlantTypesTool } from './get-all-plant-types.js';

// WRITE TOOLS (5)
import { createObservationTool } from './create-observation.js';
import { createActivityTool } from './create-activity.js';
import { updateInventoryTool } from './update-inventory.js';
import { createPlantTool } from './create-plant.js';
import { archivePlantTool } from './archive-plant.js';

// OBSERVATION MANAGEMENT (3)
import { listObservationsTool } from './list-observations.js';
import { updateObservationStatusTool } from './update-observation-status.js';
import { importObservationsTool } from './import-observations.js';

// TEAM MEMORY (4)
import { writeSessionSummaryTool } from './write-session-summary.js';
import { readTeamActivityTool } from './read-team-activity.js';
import { searchTeamMemoryTool } from './search-team-memory.js';
import { acknowledgeMemoryTool } from './acknowledge-memory.js';

// PLANT TYPE MANAGEMENT (3)
import { addPlantTypeTool } from './add-plant-type.js';
import { updatePlantTypeTool } from './update-plant-type.js';
import { reconcilePlantTypesTool } from './reconcile-plant-types.js';

// KNOWLEDGE BASE (4)
import { searchKnowledgeTool } from './search-knowledge.js';
import { listKnowledgeTool } from './list-knowledge.js';
import { addKnowledgeTool } from './add-knowledge.js';
import { updateKnowledgeTool } from './update-knowledge.js';

// OTHER (2)
import { getFarmOverviewTool } from './get-farm-overview.js';
import { regeneratePagesTool } from './regenerate-pages.js';

export const farmTools = [
  helloTool,
  // Read (7)
  queryPlantsTool,
  querySectionsTool,
  getPlantDetailTool,
  queryLogsTool,
  getInventoryTool,
  searchPlantTypesTool,
  getAllPlantTypesTool,
  // Write (5)
  createObservationTool,
  createActivityTool,
  updateInventoryTool,
  createPlantTool,
  archivePlantTool,
  // Observation management (3)
  listObservationsTool,
  updateObservationStatusTool,
  importObservationsTool,
  // Team memory (4)
  writeSessionSummaryTool,
  readTeamActivityTool,
  searchTeamMemoryTool,
  acknowledgeMemoryTool,
  // Plant type management (3)
  addPlantTypeTool,
  updatePlantTypeTool,
  reconcilePlantTypesTool,
  // Knowledge base (4)
  searchKnowledgeTool,
  listKnowledgeTool,
  addKnowledgeTool,
  updateKnowledgeTool,
  // Other (2)
  getFarmOverviewTool,
  regeneratePagesTool,
];

export { helloTool };
export { queryPlantsTool, querySectionsTool, getPlantDetailTool, queryLogsTool };
export { getInventoryTool, searchPlantTypesTool, getAllPlantTypesTool };
export { createObservationTool, createActivityTool, updateInventoryTool, createPlantTool, archivePlantTool };
export { listObservationsTool, updateObservationStatusTool, importObservationsTool };
export { writeSessionSummaryTool, readTeamActivityTool, searchTeamMemoryTool, acknowledgeMemoryTool };
export { addPlantTypeTool, updatePlantTypeTool, reconcilePlantTypesTool };
export { searchKnowledgeTool, listKnowledgeTool, addKnowledgeTool, updateKnowledgeTool };
export { getFarmOverviewTool, regeneratePagesTool };
