/** Shared paste cleanup for bulk question JSON (include inside a script block). */
function normalizeJsonPaste(text) {
  if (!text) return '';
  var trimmed = String(text).trim().replace(/^\uFEFF/, '');
  var ta = document.createElement('textarea');
  ta.innerHTML = trimmed;
  trimmed = ta.value;
  if (trimmed.indexOf('```') === 0) {
    trimmed = trimmed.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '');
  }
  trimmed = trimmed.replace(/\\\s*\r?\n/g, '\n');
  return trimmed.trim();
}

function parseJsonPaste(text) {
  return JSON.parse(normalizeJsonPaste(text));
}
