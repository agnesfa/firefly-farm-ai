import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';

const logger = baseLogger.child({ context: 'farm-plugin:tool:hello' });

const paramsSchema = z.object({
  name: z.string().optional().describe('Name to greet'),
});

export const helloTool: Tool = {
  namespace: 'farm',
  name: 'hello',
  title: 'Farm Hello',
  description: 'A simple hello tool to verify the farm plugin is loaded and working',
  paramsSchema: paramsSchema.shape,
  options: {
    readOnlyHint: true,
  },
  handler: async ({ name }) => {
    logger.info('Hello tool called', { name });

    return {
      content: [
        {
          type: 'text' as const,
          text: `Hello ${name ?? 'farmer'}! The FarmOS MCP server is up and running.`,
        },
      ],
    };
  },
};