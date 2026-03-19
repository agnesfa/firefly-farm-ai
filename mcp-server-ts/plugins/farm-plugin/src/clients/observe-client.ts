/**
 * Observation Sheet client — manages field observations via Apps Script.
 * Ported from Python observe_client.py, uses framework AxiosHttpClient.
 */

import { AppsScriptClient } from './apps-script-client.js';

export class ObservationClient extends AppsScriptClient {
  async listObservations(params: {
    status?: string;
    section?: string;
    observer?: string;
    date?: string;
    submission_id?: string;
  } = {}): Promise<any> {
    const q: Record<string, string> = { action: 'list' };
    if (params.status) q.status = params.status;
    if (params.section) q.section = params.section;
    if (params.observer) q.observer = params.observer;
    if (params.date) q.date = params.date;
    if (params.submission_id) q.submission_id = params.submission_id;
    return this.get(q);
  }

  async updateStatus(updates: Array<{
    submission_id: string;
    status: string;
    reviewer: string;
    notes?: string;
  }>): Promise<any> {
    return this.post({ action: 'update_status', updates });
  }

  async deleteImported(submissionId: string): Promise<any> {
    return this.post({ action: 'delete_imported', submission_id: submissionId });
  }

  async getMedia(submissionId: string): Promise<any> {
    return this.get({ action: 'get_media', submission_id: submissionId });
  }
}
