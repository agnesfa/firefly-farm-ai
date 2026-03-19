/**
 * Plant type description builders — embedding syntropic metadata in farmOS descriptions.
 *
 * farmOS doesn't have native syntropic fields yet (Phase 4). Instead, metadata
 * is encoded as Markdown key-value pairs in the description field.
 */

export interface PlantTypeFields {
  description?: string;
  botanical_name?: string;
  lifecycle_years?: string;
  strata?: string;
  succession_stage?: string;
  plant_functions?: string;
  crop_family?: string;
  lifespan_years?: string;
  source?: string;
}

export interface PlantTypeMetadata {
  botanical_name?: string;
  strata?: string;
  succession_stage?: string;
  plant_functions?: string;
  crop_family?: string;
  lifespan_years?: string;
  lifecycle_years?: string;
  source?: string;
}

/**
 * Build farmOS plant type description with syntropic metadata block.
 */
export function buildPlantTypeDescription(fields: PlantTypeFields): string {
  const parts: string[] = [];

  if (fields.description) {
    parts.push(fields.description);
  }

  const metadata: string[] = [];
  if (fields.botanical_name) metadata.push(`**Botanical Name:** ${fields.botanical_name}`);
  if (fields.lifecycle_years) metadata.push(`**Life Cycle:** ${fields.lifecycle_years} years`);
  if (fields.strata) metadata.push(`**Strata:** ${titleCase(fields.strata)}`);
  if (fields.succession_stage) metadata.push(`**Succession Stage:** ${titleCase(fields.succession_stage)}`);
  if (fields.plant_functions) {
    const formatted = fields.plant_functions.replace(/_/g, ' ').replace(/,/g, ', ');
    metadata.push(`**Functions:** ${titleCase(formatted)}`);
  }
  if (fields.crop_family) metadata.push(`**Family:** ${fields.crop_family}`);
  if (fields.lifespan_years) metadata.push(`**Lifespan:** ${fields.lifespan_years} years`);
  if (fields.source) metadata.push(`**Source:** ${fields.source}`);

  if (metadata.length > 0) {
    parts.push('\n\n---\n**Syntropic Agriculture Data:**\n' + metadata.join('\n'));
  }

  return parts.join('\n');
}

/**
 * Extract syntropic metadata from a plant type description.
 */
export function parsePlantTypeMetadata(descriptionText: string | null | undefined): PlantTypeMetadata {
  const metadata: PlantTypeMetadata = {};
  if (!descriptionText || !descriptionText.includes('Syntropic Agriculture Data')) {
    return metadata;
  }

  for (const line of descriptionText.split('\n')) {
    const clean = line.trim().replace(/\*\*/g, '');
    if (clean.startsWith('Botanical Name:')) {
      metadata.botanical_name = clean.split(':', 2)[1].trim();
    } else if (clean.startsWith('Strata:')) {
      metadata.strata = clean.split(':', 2)[1].trim().toLowerCase();
    } else if (clean.startsWith('Succession Stage:')) {
      metadata.succession_stage = clean.split(':', 2)[1].trim().toLowerCase();
    } else if (clean.startsWith('Functions:')) {
      const raw = clean.split(':', 2)[1].trim();
      metadata.plant_functions = raw.toLowerCase().replace(/ /g, '_').replace(/,_/g, ',');
    } else if (clean.startsWith('Family:')) {
      metadata.crop_family = clean.split(':', 2)[1].trim();
    } else if (clean.startsWith('Lifespan:')) {
      metadata.lifespan_years = clean.split(':', 2)[1].trim().replace(' years', '');
    } else if (clean.startsWith('Life Cycle:')) {
      metadata.lifecycle_years = clean.split(':', 2)[1].trim().replace(' years', '');
    } else if (clean.startsWith('Source:')) {
      metadata.source = clean.split(':', 2)[1].trim();
    }
  }

  return metadata;
}

function titleCase(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}
