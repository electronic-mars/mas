// Bridge client. The token is injected by the server when it serves index.html,
// into a meta tag: the content-security policy allows no inline script.
const MAS_TOKEN = document.querySelector('meta[name="mas-token"]').content;

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
