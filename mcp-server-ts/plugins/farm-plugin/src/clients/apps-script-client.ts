/**
 * Base client for Google Apps Script endpoints.
 *
 * Uses the framework's AxiosHttpClient for retries, timeouts, and consistent
 * error handling. All 4 Apps Script clients (observe, memory, plant-types,
 * knowledge) share the same HTTP patterns:
 *   - GET with query params for reads
 *   - POST with Content-Type: text/plain for writes (avoids CORS preflight)
 *
 * Subclasses only define the domain-specific methods.
 */

import { AxiosHttpClient, type HttpClient } from '@fireflyagents/mcp-shared-utils';

export abstract class AppsScriptClient {
  protected http: HttpClient;
  protected endpoint: string;

  constructor(endpoint: string) {
    this.endpoint = endpoint.replace(/\/+$/, '');
    this.http = new AxiosHttpClient({
      baseURL: this.endpoint,
      timeout: 30_000,
    });
  }

  /**
   * GET request with query params appended to the endpoint URL.
   * Apps Script responds to GET at the deployment URL with query string params.
   */
  protected async get(params: Record<string, string>): Promise<any> {
    const qs = new URLSearchParams(params).toString();
    // AxiosHttpClient.get() takes a URL relative to baseURL
    // Since baseURL IS the full endpoint, pass the query string as the path
    const resp = await this.http.get(`?${qs}`);
    return resp.data;
  }

  /**
   * POST request with JSON payload as text/plain body.
   * Apps Script requires text/plain to avoid CORS preflight on anonymous POST.
   */
  protected async post(payload: Record<string, any>): Promise<any> {
    const resp = await this.http.post('', JSON.stringify(payload), {
      headers: { 'Content-Type': 'text/plain' },
    });
    return resp.data;
  }
}
