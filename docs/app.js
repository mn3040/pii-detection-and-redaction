// Wires the UI to REGEX_DETECTORS (defined in detectors.js).
// Three output views: annotated (colour-highlighted), masked, detections table.

const TYPE_COLOR = {
  SSN:            'var(--c-ssn)',
  EMAIL:          'var(--c-email)',
  PHONE:          'var(--c-phone)',
  CREDIT_CARD:    'var(--c-cc)',
  IP_ADDRESS:     'var(--c-ip)',
  STREET_ADDRESS: 'var(--c-addr)',
  DATE_OF_BIRTH:  'var(--c-dob)',
};

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// ── Overlap resolution (mirrors redactor.py _resolve_overlaps) ────────────────
function resolveOverlaps(detections) {
  const ranked = [...detections].sort((a, b) => {
    if (b.confidence !== a.confidence) return b.confidence - a.confidence;
    return (b.end - b.start) - (a.end - a.start);
  });
  const chosen = [];
  const occupied = [];
  for (const d of ranked) {
    if (occupied.some(([s, e]) => d.start < e && d.end > s)) continue;
    chosen.push(d);
    occupied.push([d.start, d.end]);
  }
  return chosen;
}

// ── Annotated view: inject <mark> spans into plain text ──────────────────────
function buildAnnotatedHTML(text, detections) {
  if (!detections.length) return escapeHTML(text);

  const nonOverlapping = resolveOverlaps(detections)
    .sort((a, b) => a.start - b.start);

  let html = '';
  let cursor = 0;
  for (const d of nonOverlapping) {
    html += escapeHTML(text.slice(cursor, d.start));
    html += `<mark class="pii-mark pii-${d.entityType}" data-type="${d.entityType}">${escapeHTML(d.text)}</mark>`;
    cursor = d.end;
  }
  html += escapeHTML(text.slice(cursor));
  return html;
}

function escapeHTML(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Masked view ───────────────────────────────────────────────────────────────
function buildMaskedText(text, detections) {
  const nonOverlapping = resolveOverlaps(detections)
    .sort((a, b) => b.start - a.start);   // reverse order so offsets stay valid
  let masked = text;
  for (const d of nonOverlapping) {
    masked = masked.slice(0, d.start) + `[REDACTED_${d.entityType}]` + masked.slice(d.end);
  }
  return masked;
}

// ── Detections table ──────────────────────────────────────────────────────────
function buildTable(detections) {
  const tbody = document.querySelector('#detections-table tbody');
  tbody.innerHTML = '';

  if (!detections.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);font-family:\'IBM Plex Mono\',monospace;font-size:0.82rem;padding:0.75rem">No PII detected.</td></tr>';
    return;
  }

  for (const d of detections) {
    const color = TYPE_COLOR[d.entityType] || 'var(--muted)';
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="type-pill pii-${d.entityType}">${d.entityType}</span></td>
      <td>${escapeHTML(d.text)}</td>
      <td style="color:var(--muted)">${d.start}–${d.end}</td>
      <td style="color:var(--muted)">${d.confidence.toFixed(2)}</td>
    `;
    tbody.appendChild(row);
  }
}

// ── Main scan ─────────────────────────────────────────────────────────────────
function runScan() {
  const text = document.getElementById('input-text').value;

  let allDetections = [];
  for (const detector of REGEX_DETECTORS) {
    allDetections = allDetections.concat(detector.detect(text));
  }

  // Annotated tab
  const annotatedEl = document.getElementById('annotated-view');
  annotatedEl.classList.remove('empty-state');
  if (text.trim()) {
    annotatedEl.innerHTML = buildAnnotatedHTML(text, allDetections);
  } else {
    annotatedEl.classList.add('empty-state');
    annotatedEl.textContent = '← Scan some text to see detections highlighted inline.';
  }

  // Masked tab
  const maskedEl = document.getElementById('masked-view');
  maskedEl.classList.remove('empty-state');
  maskedEl.textContent = text.trim() ? buildMaskedText(text, allDetections) : '';

  // Table tab
  buildTable(allDetections);
}

document.getElementById('scan-btn').addEventListener('click', runScan);

// Also scan on Ctrl/Cmd + Enter
document.getElementById('input-text').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runScan();
});
