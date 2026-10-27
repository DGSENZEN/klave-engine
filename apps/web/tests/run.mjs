// Compile the browser-independent client code with the existing TypeScript
// compiler, then exercise it with Node's built-in test runner (no extra deps).
import { mkdtempSync, rmSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const output = mkdtempSync(join(tmpdir(), 'klave-web-tests-'));
try {
  const compile = spawnSync(process.execPath, [
    'node_modules/typescript/bin/tsc', 'lib/api.ts', 'lib/uploads.ts', 'lib/httpErrors.ts', 'lib/sessionReturn.ts', 'lib/apiProxy.ts', 'lib/collab.ts', 'lib/recorrido/motor.ts', 'lib/recorrido/colocar.ts', 'lib/recorrido/progreso.ts', 'lib/recorrido/capitulos/index.ts', 'lib/recorrido/teclas.ts',
    '--outDir', output, '--module', 'commonjs', '--target', 'ES2022', '--skipLibCheck',
  ], { stdio: 'inherit' });
  if (compile.status !== 0) process.exitCode = compile.status ?? 1;
  else {
    const result = spawnSync(process.execPath, ['--test', ...readdirSync('tests').filter((file) => file.endsWith('.test.mjs')).map((file) => join('tests', file))], {
      stdio: 'inherit', env: { ...process.env, KLAVE_TEST_LIB_DIR: output },
    });
    process.exitCode = result.status ?? 1;
  }
} finally {
  rmSync(output, { recursive: true, force: true });
}
