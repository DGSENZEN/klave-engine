import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { join } from 'node:path';
const { uploadProject, ApiError } = createRequire(import.meta.url)(join(process.env.KLAVE_TEST_LIB_DIR, 'api.js'));

// The request has already stored the files when enqueueing fails. A retry
// must open that project rather than upload the same drawings a second time.
test('a full queue returns the saved project and a processing warning', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: {
    error_type: 'processing_queue_full', project_id: 'obra_guardada',
    message: 'La cola está llena.',
  } }, { status: 429 }));
  const result = await uploadProject([new File(['drawing'], 'plano.dxf')]);
  assert.equal(result.project_id, 'obra_guardada');
  assert.ok(result.warnings.length > 0);
});

test('a rate-limited upload without a saved project remains an error', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: {
    error_type: 'rate_limited', message: 'Espera un momento.',
  } }, { status: 429 }));
  await assert.rejects(uploadProject([new File(['drawing'], 'plano.dxf')]), ApiError);
});

const { validateDrawingFiles } = createRequire(import.meta.url)(join(process.env.KLAVE_TEST_LIB_DIR, 'uploads.js'));
const drawing = (name = 'plano.dxf', content = 'drawing') => new File([content], name);
test('selection accepts 40 supported drawings including uppercase extensions', () => {
  assert.equal(validateDrawingFiles(Array.from({ length: 40 }, () => drawing('PLANO.DXF'))), null);
});
test('selection rejects 41 drawings before sending any upload', () => {
  assert.ok(validateDrawingFiles(Array.from({ length: 41 }, () => drawing())));
});
test('mixed selection reports unsupported files rather than silently omitting them', () => {
  assert.ok(validateDrawingFiles([drawing(), drawing('notas.pdf')]));
});
test('an empty drawing cannot create a project', () => {
  assert.ok(validateDrawingFiles([drawing('vacio.dxf', '')]));
});

test('selection uses the configured byte boundary', () => {
  const limits = { max_files: 40, max_file_bytes: 100 };
  assert.equal(validateDrawingFiles([{ name: 'plan.dxf', size: 100 }], limits), null);
  assert.ok(validateDrawingFiles([{ name: 'plan.dxf', size: 101 }], limits));
  assert.equal(validateDrawingFiles([{ name: 'plan.dxf', size: 101 }],
    { max_files: 40, max_file_bytes: 200 }), null);
});

const { uploadErrorMessage, MAX_BATCH_BYTES, DEFAULT_MAX_FILE_BYTES } =
  createRequire(import.meta.url)(join(process.env.KLAVE_TEST_LIB_DIR, 'uploads.js'));
const MIB = 1024 * 1024;

test('without workspace limits a file over 100 MB is rejected by name', () => {
  assert.equal(DEFAULT_MAX_FILE_BYTES, 100 * MIB);
  assert.equal(validateDrawingFiles([{ name: 'plan.dwg', size: 100 * MIB }]), null);
  const message = validateDrawingFiles([{ name: 'grande.dwg', size: 100 * MIB + 1 }]);
  assert.match(message, /«grande\.dwg»/);
  assert.match(message, /100 MB/);
});

test('a batch over the request cap is rejected with its total and the parts hint', () => {
  // Cada archivo cabe; la suma no. Debe quedar bajo los 120 MB decimales del proxy.
  assert.ok(MAX_BATCH_BYTES < 120 * 1000 * 1000);
  const half = Math.floor(MAX_BATCH_BYTES / 2);
  assert.equal(validateDrawingFiles([{ name: 'a.dwg', size: half }, { name: 'b.dwg', size: half }]), null);
  const message = validateDrawingFiles([
    { name: 'a.dwg', size: half }, { name: 'b.dwg', size: half }, { name: 'c.dwg', size: 2 * MIB },
  ]);
  assert.match(message, /suma 112 MB/);
  assert.match(message, /Hojas del proyecto/);
});

test('a 413 from the API explains the size limit instead of a generic failure', () => {
  const tooLarge = new ApiError(413, '/projects/upload', { error_type: 'upload_too_large', max_upload_bytes: 100 * MIB });
  assert.match(uploadErrorMessage(tooLarge, 'genérico'), /100 MB por archivo/);
  const tooMany = new ApiError(413, '/projects/upload', { error_type: 'too_many_files', message: 'Un proyecto lleva hasta 40 hojas.' });
  assert.equal(uploadErrorMessage(tooMany, 'genérico'), 'Un proyecto lleva hasta 40 hojas.');
  assert.equal(uploadErrorMessage(new TypeError('Failed to fetch'), 'genérico'), 'genérico');
});
