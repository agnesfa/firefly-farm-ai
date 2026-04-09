export { parseDate, formatPlantedLabel, buildAssetName, formatTimestamp } from './dates.js';
export { parseAssetName } from './names.js';
export type { ParsedAssetName } from './names.js';
export { formatPlantAsset, formatLog, formatPlantType, formatSectionFromAssets, summarizeKbEntries } from './formatters.js';
export { buildPlantTypeDescription, parsePlantTypeMetadata } from './plant-type-metadata.js';
export type { PlantTypeFields, PlantTypeMetadata } from './plant-type-metadata.js';
export { extractMemorySummaries, countKbEntries } from './apps-script-unwrap.js';

export {
  SECTION_HEALTH, TOPIC_FARMOS_MAP,
  assessStrataCoverage, assessActivityRecency, assessSuccessionBalance,
  assessSectionHealth, findTransplantReady,
  detectKnowledgeGaps, detectDecisionGaps, detectLoggingGaps,
  classifyByDirection, assessFarmMaturity, assessSystemMaturity, assessTeamMaturity,
} from './semantics.js';

/** Hardcoded UUID for the "plant" unit in farmOS. */
export const PLANT_UNIT_UUID = '2371b79e-a87b-4152-b6e4-ea6a9ed37fd0';
