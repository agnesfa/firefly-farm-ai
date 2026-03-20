/**
 * Team Memory client — manages session summaries via Apps Script.
 * Ported from Python memory_client.py, uses framework AxiosHttpClient.
 */

import { AppsScriptClient } from './apps-script-client.js';

export class MemoryClient extends AppsScriptClient {
  async writeSummary(params: {
    user: string;
    topics?: string;
    decisions?: string;
    farmos_changes?: string;
    questions?: string;
    summary?: string;
    skip?: boolean;
  }): Promise<any> {
    return this.post({
      action: 'write_summary',
      user: params.user,
      topics: params.topics ?? '',
      decisions: params.decisions ?? '',
      farmos_changes: params.farmos_changes ?? '',
      questions: params.questions ?? '',
      summary: params.summary ?? '',
      skip: params.skip ?? false,
    });
  }

  async readActivity(days = 7, user?: string, limit = 20, onlyFreshFor?: string): Promise<any> {
    const q: Record<string, string> = { action: 'list', days: String(days), limit: String(limit) };
    if (user) q.user = user;
    if (onlyFreshFor) q.only_fresh_for = onlyFreshFor;
    return this.get(q);
  }

  async searchMemory(query: string, days = 30): Promise<any> {
    return this.get({ action: 'search', query, days: String(days) });
  }

  async acknowledgeMemory(summaryId: string, user: string): Promise<any> {
    return this.post({
      action: 'acknowledge',
      summary_id: summaryId,
      user,
    });
  }
}
