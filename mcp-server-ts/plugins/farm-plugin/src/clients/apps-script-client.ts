/**
 * Base client for Google Apps Script endpoints.
 *
 * Uses native fetch instead of AxiosHttpClient because Google Apps Script
 * deployment URLs return a 302 redirect chain (script.google.com →
 * script.googleusercontent.com) that axios doesn't follow correctly,
 * returning Google sign-in HTML instead of JSON data.
 *
 * Native fetch with redirect: 'follow' handles this reliably.
 *
 * All 4 Apps Script clients (observe, memory, plant-types, knowledge)
 * share the same HTTP patterns:
 *   - GET with query params for reads
 *   - POST with Content-Type: text/plain for writes (avoids CORS preflight)
 *
 * Subclasses only define the domain-specific methods.
 */

import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';

const logger = baseLogger.child({ context: 'farm-plugin:apps-script-client' });

export abstract class AppsScriptClient {
  protected endpoint: string;

  constructor(endpoint: string) {
    this.endpoint = endpoint.replace(/\/+$/, '');
  }

  /**
   * GET request with query params appended to the endpoint URL.
   * Apps Script responds to GET at the deployment URL with query string params.
   */
  protected async get(params: Record<string, string>): Promise<any> {
    const qs = new URLSearchParams(params).toString();
    const url = `${this.endpoint}?${qs}`;

    logger.debug('Apps Script GET', { url: this.endpoint, params });

    const resp = await fetch(url, {
      method: 'GET',
      redirect: 'follow',
    });

    if (!resp.ok) {
      throw new Error(`Apps Script GET failed: HTTP ${resp.status}`);
    }

    const text = await resp.text();
    try {
      return JSON.parse(text);
    } catch {
      // If the response isn't JSON, it's likely a Google sign-in page
      logger.error('Apps Script returned non-JSON response', {
        status: resp.status,
        contentType: resp.headers.get('content-type'),
        bodyPreview: text.substring(0, 200),
      });
      throw new Error('Apps Script returned non-JSON response (possible auth/redirect issue)');
    }
  }

  /**
   * POST request with JSON payload as text/plain body.
   * Apps Script requires text/plain to avoid CORS preflight on anonymous POST.
   */
  protected async post(payload: Record<string, any>): Promise<any> {
    logger.debug('Apps Script POST', { url: this.endpoint });

    const resp = await fetch(this.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify(payload),
      redirect: 'follow',
    });

    if (!resp.ok) {
      throw new Error(`Apps Script POST failed: HTTP ${resp.status}`);
    }

    const text = await resp.text();
    try {
      return JSON.parse(text);
    } catch {
      logger.error('Apps Script returned non-JSON response', {
        status: resp.status,
        contentType: resp.headers.get('content-type'),
        bodyPreview: text.substring(0, 200),
      });
      throw new Error('Apps Script returned non-JSON response (possible auth/redirect issue)');
    }
  }
}
