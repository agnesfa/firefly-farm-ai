/**
 * Date utilities for farmOS data processing.
 *
 * All dates are in AEST (UTC+10) for the farm's location in NSW, Australia.
 */

/** AEST offset in milliseconds (UTC+10) */
const AEST_OFFSET_MS = 10 * 60 * 60 * 1000;

const MONTH_NAMES: Record<string, number> = {
  JANUARY: 0, FEBRUARY: 1, MARCH: 2, APRIL: 3,
  MAY: 4, JUNE: 5, JULY: 6, AUGUST: 7,
  SEPTEMBER: 8, OCTOBER: 9, NOVEMBER: 10, DECEMBER: 11,
};

const MONTH_ABBREVS = [
  'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
  'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC',
];

/**
 * ADR 0008 I12: refuse timestamps more than 24h past now. 24h grace
 * accommodates AEST↔UTC edge cases without admitting year-typos.
 */
function guardFutureTs(ts: number, raw: string): number {
  const nowTs = Math.floor(Date.now() / 1000);
  if (ts > nowTs + 86400) {
    const human = new Date(ts * 1000).toISOString().slice(0, 10);
    throw new Error(
      `Refusing future-dated timestamp: '${raw}' resolved to ${human}, ` +
      `more than 24h after now. Possible year-typo (e.g. '2026-12-18' ` +
      `when you meant '2025-12-18'). See ADR 0008 I12.`,
    );
  }
  return ts;
}

/**
 * Parse date string to Unix timestamp (farmOS format).
 *
 * Handles: ISO "2025-10-09", ISO with time "2026-03-09T03:15:00.000Z",
 * text "2025-MARCH-20 to 24TH", fallback to now.
 *
 * Throws if input resolves to a timestamp more than 24h in the future
 * (ADR 0008 I12).
 */
export function parseDate(dateStr: string | null | undefined): number {
  if (!dateStr) {
    return Math.floor(Date.now() / 1000);
  }

  // ISO format: 2025-10-09
  const isoMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) {
    const dt = new Date(Date.UTC(
      parseInt(isoMatch[1]),
      parseInt(isoMatch[2]) - 1,
      parseInt(isoMatch[3]),
    ));
    return guardFutureTs(Math.floor((dt.getTime() - AEST_OFFSET_MS) / 1000), dateStr);
  }

  // ISO with time: 2026-03-09T03:15:00.000Z
  if (dateStr.includes('T')) {
    const dt = new Date(dateStr);
    if (!isNaN(dt.getTime())) {
      return guardFutureTs(Math.floor(dt.getTime() / 1000), dateStr);
    }
  }

  // "2025-MARCH-20 to 24TH" format
  const parts = dateStr.toUpperCase().replace(',', '').split('-');
  if (parts.length >= 2) {
    const year = parseInt(parts[0].trim());
    const monthStr = parts[1].trim();
    if (!isNaN(year) && monthStr in MONTH_NAMES) {
      let day = 1;
      if (parts.length >= 3) {
        const dayStr = parts[2].trim().split(/\s/)[0];
        const dayNum = parseInt(dayStr.replace(/\D/g, ''));
        if (!isNaN(dayNum) && dayNum > 0) {
          day = dayNum;
        }
      }
      const dt = new Date(Date.UTC(year, MONTH_NAMES[monthStr], day));
      return guardFutureTs(Math.floor((dt.getTime() - AEST_OFFSET_MS) / 1000), dateStr);
    }
  }

  // Fallback: now (unparseable input is safe; a future-dated successful
  // parse is not — guarded above).
  return Math.floor(Date.now() / 1000);
}

/**
 * Format first_planted date for plant asset name.
 *
 * "2025-04-25" → "25 APR 2025", "April 2025" → "APR 2025", "" → "SPRING 2025"
 */
export function formatPlantedLabel(dateStr: string | null | undefined): string {
  if (!dateStr) return 'SPRING 2025';

  // ISO format: 2025-04-25
  const isoMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) {
    const day = parseInt(isoMatch[3]);
    const month = MONTH_ABBREVS[parseInt(isoMatch[2]) - 1];
    return `${day} ${month} ${isoMatch[1]}`;
  }

  // Text format: "April 2025"
  const textMatch = dateStr.match(/^([A-Za-z]+)\s+(\d{4})$/);
  if (textMatch) {
    const monthUpper = textMatch[1].toUpperCase();
    for (const [fullName, idx] of Object.entries(MONTH_NAMES)) {
      if (fullName === monthUpper) {
        return `${MONTH_ABBREVS[idx]} ${textMatch[2]}`;
      }
    }
  }

  return dateStr.toUpperCase();
}

/**
 * Build a plant asset name following farmOS conventions.
 * Format: "{planted_date_label} - {farmos_name} - {section_id}"
 */
export function buildAssetName(plantedDate: string, farmosName: string, sectionId: string): string {
  const label = formatPlantedLabel(plantedDate);
  return `${label} - ${farmosName} - ${sectionId}`;
}

/**
 * Format a Unix timestamp or ISO string to human-readable date in AEST.
 */
export function formatTimestamp(unixTs: unknown): string {
  if (!unixTs) return 'unknown';

  // Try as Unix timestamp
  const numVal = typeof unixTs === 'string' ? parseInt(unixTs) : typeof unixTs === 'number' ? unixTs : NaN;
  if (!isNaN(numVal) && numVal > 1000000000 && numVal < 10000000000) {
    const dt = new Date((numVal * 1000) + AEST_OFFSET_MS);
    return formatDateAEST(dt);
  }

  // Try as ISO string
  if (typeof unixTs === 'string') {
    const dt = new Date(unixTs);
    if (!isNaN(dt.getTime())) {
      const aest = new Date(dt.getTime() + AEST_OFFSET_MS);
      return formatDateAEST(aest);
    }
  }

  return String(unixTs);
}

function formatDateAEST(dt: Date): string {
  const y = dt.getUTCFullYear();
  const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const d = String(dt.getUTCDate()).padStart(2, '0');
  const h = String(dt.getUTCHours()).padStart(2, '0');
  const min = String(dt.getUTCMinutes()).padStart(2, '0');
  return `${y}-${m}-${d} ${h}:${min}`;
}
