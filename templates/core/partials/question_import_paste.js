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
  trimmed = trimmed.replace(/\\([\[\]{}])/g, '$1');
  // LaTeX/backslash-heavy text: \( \) \_ \times etc. are invalid unless escaped as \\
  trimmed = trimmed.replace(/(?<!\\)\\(?!["\\/bfnrt]|u(?:[0-9a-fA-F]{4}))/g, '\\\\');
  // Curly “smart” quotes (WhatsApp, Word, etc.) are invalid in JSON
  trimmed = trimmed
    .replace(/[\u201C\u201D\u201E\u2033\u00AB\u00BB]/g, '"')
    .replace(/[\u2018\u2019\u201A]/g, "'");
  return trimmed.trim();
}

function parseJsonPaste(text) {
  return JSON.parse(normalizeJsonPaste(text));
}
