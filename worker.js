// 별도 작업 공간(Web Worker)에서 Pyodide로 model.py 실행 — 화면이 멈추지 않도록 계산을 분리
const PYODIDE_BASE = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
let py = null;
let ready = null;
let chain = Promise.resolve();

function status(text, pct) { postMessage({ type: 'status', text, pct }); }

async function boot() {
  status('Python 실행 환경(Pyodide) 내려받는 중…', 5);
  importScripts(PYODIDE_BASE + 'pyodide.js');
  py = await loadPyodide({ indexURL: PYODIDE_BASE });
  status('numpy 준비 중…', 15);
  await py.loadPackage(['numpy', 'micropip']);
  status('openpyxl(엑셀 읽기) 설치 중…', 22);
  await py.runPythonAsync("import micropip\nawait micropip.install('openpyxl==3.1.5')");
  const res = await fetch('./model.py', { cache: 'no-cache' });
  if (!res.ok) throw new Error('model.py를 불러올 수 없습니다 (HTTP ' + res.status + ')');
  await py.runPythonAsync(await res.text());
  status('Python 준비 완료', 28);
}

// 엑셀 바이트를 Python bytes로 넘김
function setBytes(name, buf) {
  if (buf == null) { py.globals.set(name, null); return; }
  py.globals.set(name + '_js', new Uint8Array(buf));
  py.runPython(name + ' = ' + name + '_js.to_py()\ndel ' + name + '_js');
}

async function handle({ id, fn, args, buffers }) {
  try {
    if (!ready) ready = boot();
    await ready;
    let out;
    if (fn === 'load_level') {
      setBytes('_raw', buffers[0]);
      py.globals.set('_key', args[0]);
      out = py.runPython('load_level(_key, _raw)');
      py.runPython('del _raw, _key');
    } else if (fn === 'load_aux') {
      setBytes('_cls', buffers[0]);
      setBytes('_stats', buffers[1]);
      out = py.runPython('load_aux(_cls, _stats)');
      py.runPython('del _cls, _stats');
    } else {
      const f = py.globals.get(fn);
      if (!f) throw new Error('알 수 없는 함수: ' + fn);
      out = f(...(args || []));
      f.destroy();
    }
    postMessage({ id, ok: true, result: JSON.parse(out) });
  } catch (err) {
    let msg = String(err && err.message ? err.message : err);
    const m = msg.match(/(ValueError|KeyError|IndexError|TypeError|LinAlgError)[^\n]*/g);
    if (m) msg = m[m.length - 1];
    postMessage({ id, ok: false, error: msg });
  }
}

onmessage = (e) => { chain = chain.then(() => handle(e.data)); };
