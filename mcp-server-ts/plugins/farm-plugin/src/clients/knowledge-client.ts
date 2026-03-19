/**
 * Knowledge Base client — manages farm knowledge entries via Apps Script.
 * Ported from Python knowledge_client.py, uses framework AxiosHttpClient.
 */

import { AppsScriptClient } from './apps-script-client.js';

export class KnowledgeClient extends AppsScriptClient {
  async listEntries(category?: string, limit = 50, offset = 0): Promise<any> {
    const q: Record<string, string> = { action: 'list', limit: String(limit), offset: String(offset) };
    if (category) q.category = category;
    return this.get(q);
  }

  async search(query: string, category?: string): Promise<any> {
    const q: Record<string, string> = { action: 'search', query };
    if (category) q.category = category;
    return this.get(q);
  }

  async add(fields: Record<string, any>): Promise<any> {
    return this.post({ ...fields, action: 'add' });
  }

  async update(entryId: string, fields: Record<string, any>): Promise<any> {
    return this.post({ ...fields, action: 'update', entry_id: entryId });
  }
}
