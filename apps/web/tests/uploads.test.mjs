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
