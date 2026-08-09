// Bridge client. The token is injected by the server when it serves index.html.
const MAS_TOKEN = window.__MAS_TOKEN__;

export async function call(method, payload = null) {
  const res = await fetch(`/api/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-MAS-Token': MAS_TOKEN },
    body: payload ? JSON.stringify(payload) : '',
  });
  const data = await res.json().catch(() => ({ ok: false, error: 'response could not be parsed' }));
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data.result;
}
