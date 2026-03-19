/**
 * Plant asset name parsing and building utilities.
 *
 * farmOS asset names follow: "{date} - {species} - {section_id}"
 * Species can contain " - " (e.g., "Basil - Sweet (Classic)")
 */

export interface ParsedAssetName {
  plantedDate: string;
  species: string;
  section: string;
}

/**
 * Parse a farmOS plant asset name into components.
 *
 * Uses split + rsplit logic: date is FIRST part, section is LAST part,
 * species is everything in between (handles species with " - ").
 */
export function parseAssetName(name: string): ParsedAssetName {
  const parts = name.split(' - ');
  if (parts.length >= 3) {
    return {
      plantedDate: parts[0],
      section: parts[parts.length - 1],
      species: parts.slice(1, -1).join(' - '),
    };
  }
  if (parts.length === 2) {
    return {
      plantedDate: parts[0],
      species: parts[1],
      section: '',
    };
  }
  return {
    plantedDate: '',
    species: name,
    section: '',
  };
}
