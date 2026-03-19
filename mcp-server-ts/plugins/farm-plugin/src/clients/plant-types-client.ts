/**
 * Plant Types Sheet client — manages plant type taxonomy via Apps Script.
 * Ported from Python plant_types_client.py, uses framework AxiosHttpClient.
 */

import { AppsScriptClient } from './apps-script-client.js';

export class PlantTypesClient extends AppsScriptClient {
  async listAll(): Promise<any> {
    return this.get({ action: 'list' });
  }

  async search(query: string): Promise<any> {
    return this.get({ action: 'search', query });
  }

  async add(fields: Record<string, any>): Promise<any> {
    return this.post({ ...fields, action: 'add' });
  }

  async update(farmosName: string, fields: Record<string, any>): Promise<any> {
    return this.post({ ...fields, action: 'update', farmos_name: farmosName });
  }

  async getReconcileData(): Promise<any> {
    return this.get({ action: 'reconcile' });
  }
}
