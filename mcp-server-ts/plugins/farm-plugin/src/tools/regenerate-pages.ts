import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';

export const regeneratePagesTool: Tool = {
  namespace: 'fc',
  name: 'regenerate_pages',
  title: 'Regenerate QR Pages',
  description: 'Regenerate QR landing pages from live farmOS data and optionally push to GitHub Pages.\n\nRuns the full pipeline:\n1. Export farmOS data → sections.json (enriched with inventory counts, log history)\n2. Generate HTML pages from sections.json + plant_types.csv\n3. Git commit and push to trigger GitHub Pages deployment\n\nThis should be run after importing observations or making changes in farmOS\nto update the public QR landing pages.\n\nArgs:\n    push_to_github: If True (default), commit and push changes to GitHub Pages.\n                   Set to False for a dry-run that generates but doesn\'t deploy.\n\nReturns:\n    Status of each pipeline step.',
  paramsSchema: z.object({
    push_to_github: z.boolean().default(true).describe('Whether to push to GitHub Pages'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async () => {
    // This tool requires local git repo + Python scripts — not available on Railway
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'deferred',
        message: 'Page regeneration is not available on the remote server. '
          + 'Run the regenerate_pages tool locally on Agnes\'s machine, '
          + 'or use: python scripts/export_farmos.py --sections-json && python scripts/generate_site.py',
        pages_url: 'https://agnesfa.github.io/firefly-farm-ai/',
      }, null, 2) }],
    };
  },
};
