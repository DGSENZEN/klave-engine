/**
 * Drawn screens of the app for the portada. They are illustrations with
 * sample data, built in the page's own ink-and-orange language, each one
 * showing a stage of the obra's real tablero. They play their sequence when
 * they scroll into view (see RutaPortada); without script, or with reduced
 * motion, they simply show their finished state.
 */

import type { CSSProperties, ReactNode } from "react";

const NODOS = ["Planos", "Disciplinas", "Revisión", "Catálogo", "Presupuesto", "Programa"];

const i = (n: number) => ({ "--i": n }) as CSSProperties;

function Pantalla({
  nodo,
  titulo,
  children,
  nota = "Pantalla ilustrativa con datos de ejemplo.",
}: {
  nodo: number;
  titulo: string;
  children: ReactNode;
  nota?: string;
}) {
  return (
    <figure className="l68-app" data-play>
      <div className="l68-app-bar">
        <span className="l68-app-crumb">
          <span className="v-obra">
            Obra de ejemplo <span aria-hidden="true">/</span>{" "}
          </span>
          <b>{titulo}</b>
        </span>
        <span className="l68-app-nodes" aria-label={`Etapa ${nodo + 1} de 6: ${NODOS[nodo]}`}>
          {NODOS.map((n, k) => (
            <i key={n} className={k < nodo ? "is-done" : k === nodo ? "is-now" : undefined} />
          ))}
        </span>
      </div>
      <div className="l68-app-body">{children}</div>
      <figcaption>{nota}</figcaption>
    </figure>
  );
}

/* 01 · Planos ------------------------------------------------------------ */

const HOJAS: [string, string, string][] = [
  ["E-01", "Cimentación.dwg", "Estructura"],
  ["E-02", "Estructura nivel 1.dwg", "Estructura"],
  ["E-03", "Losas.dxf", "Estructura"],
  ["IE-01", "Instalación eléctrica.dwg", "Levantamiento"],
  ["IH-01", "Hidrosanitaria.dwg", "Levantamiento"],
  ["A-01", "Planta arquitectónica.dwg", "Fondo · no se cobra"],
];

export function VistaPlanos() {
  return (
    <Pantalla nodo={0} titulo="Planos">
      <div className="v-drop">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 16V4m0 0-5 5m5-5 5 5M4 20h16" />
        </svg>
        Suelta el juego de planos: DWG o DXF, hasta 40 hojas
      </div>
      <ul className="v-sheets">
        {HOJAS.map(([clave, archivo, destino], n) => (
          <li key={clave} style={i(n)}>
            <span className="l68-mono">{clave}</span>
            <span className="v-file">{archivo}</span>
            <span className="v-state">
              <i>Leyendo…</i>
              <b className={destino === "Estructura" ? "is-deep" : undefined}>{destino}</b>
            </span>
          </li>
        ))}
      </ul>
      <p className="v-sum">
        6 hojas · unidades: centímetros · <b>3 se leen a fondo</b>
      </p>
    </Pantalla>
  );
}

/* 02 · Disciplinas (visor) ----------------------------------------------- */

export function VistaVisor() {
  const xs = [70, 250, 430];
  const ys = [70, 190, 310];
  return (
    <Pantalla nodo={1} titulo="Plano · E-02">
      <div className="v-visor">
        <div className="v-tools">
          <span className="is-on">Todas</span>
          <span>Cimentación</span>
          <span>Estructura</span>
          <span className="v-tool-end">
            Medir <kbd>M</kbd>
          </span>
        </div>
        <svg
          className="v-plan"
          viewBox="0 0 500 370"
          role="img"
          aria-label="Planta de ejemplo: el lector marca zapatas, castillos y trabes; la trabe T-3 queda seleccionada."
        >
          {xs.map((x) => (
            <line key={`x${x}`} className="axis" x1={x} y1={28} x2={x} y2={355} />
          ))}
          {ys.map((y) => (
            <line key={`y${y}`} className="axis" x1={28} y1={y} x2={485} y2={y} />
          ))}
          {["A", "B", "C"].map((k, n) => (
            <g key={k}>
              <circle className="bubble" cx={xs[n]} cy={16} r={13} />
              <text x={xs[n]} y={21} textAnchor="middle">{k}</text>
            </g>
          ))}
          {["1", "2", "3"].map((k, n) => (
            <g key={k}>
              <circle className="bubble" cx={16} cy={ys[n]} r={13} />
              <text x={16} y={ys[n] + 5} textAnchor="middle">{k}</text>
            </g>
          ))}
          <g className="fam fam-zap">
            {xs.flatMap((x) => ys.map((y) => <rect key={`z${x}${y}`} x={x - 22} y={y - 22} width={44} height={44} />))}
          </g>
          <g className="fam fam-beam">
            {ys.flatMap((y) =>
              [0, 1].map((n) => <rect key={`h${y}${n}`} x={xs[n] + 7} y={y - 5} width={xs[n + 1] - xs[n] - 14} height={10} />),
            )}
            {xs.flatMap((x) =>
              [0, 1].map((n) => <rect key={`v${x}${n}`} x={x - 5} y={ys[n] + 7} width={10} height={ys[n + 1] - ys[n] - 14} />),
            )}
          </g>
          <g className="fam fam-col">
            {xs.flatMap((x) => ys.map((y) => <rect key={`c${x}${y}`} x={x - 7} y={y - 7} width={14} height={14} />))}
          </g>
          <rect className="v-pick" x={xs[0] + 7} y={ys[1] - 5} width={xs[1] - xs[0] - 14} height={10} />
          <rect className="scan" x={-6} y={0} width={6} height={370} />
        </svg>
        <dl className="v-insp">
          <div><dt>Marca</dt><dd className="is-key">T-3</dd></div>
          <div><dt>Familia</dt><dd>Trabe</dd></div>
          <div><dt>Sección</dt><dd>20×40, del cuadro de trabes</dd></div>
          <div><dt>Ejes</dt><dd className="l68-mono">2 · A–B</dd></div>
          <div><dt>Longitud</dt><dd className="l68-mono">6.40 m</dd></div>
          <div><dt>Hoja</dt><dd className="l68-mono">E-02</dd></div>
          <div><dt>Lectura</dt><dd>Regla determinista</dd></div>
        </dl>
      </div>
    </Pantalla>
  );
}

/* 03 · Revisión ----------------------------------------------------------- */

const COLA: [string, string, string, string, string, string?][] = [
  ["Z-1", "Zapata", "120×120×30", "Confirmada", "ok"],
  ["K-1", "Castillo", "3.10 m", "Confirmada", "ok"],
  ["K-7", "Castillo", "3.10 m", "Excluida", "no", "duplicada en E-03"],
  ["T-3", "Trabe", "6.40 m", "Confirmada", "ok"],
  ["L-2", "Losa", "18.40 m²", "En duda", "q"],
];

export function VistaRevision() {
  return (
    <Pantalla nodo={2} titulo="Revisión">
      <div className="v-queue">
        <div className="v-queue-head">
          <span>Detecciones por revisar</span>
          <span className="l68-mono">
            <b data-cuenta="5" data-dur="3400">5</b> de 5
          </span>
        </div>
        <ol>
          <span className="v-cursor" aria-hidden="true" />
          {COLA.map(([marca, familia, medida, veredicto, tipo, motivo], n) => (
            <li key={marca} style={i(n)} className={marca === "T-3" ? "is-traced" : undefined}>
              <span className="l68-mono">{marca}</span>
              <span>{familia}</span>
              <span className="l68-mono">{medida}</span>
              <span className={`v-verdict is-${tipo}`}>
                {veredicto}
                {motivo && <span className="v-long"> · {motivo}</span>}
              </span>
            </li>
          ))}
        </ol>
        <div className="v-keys" aria-hidden="true">
          <span className="k-c"><kbd>C</kbd> Confirmar</span>
          <span className="k-x"><kbd>X</kbd> Excluir</span>
          <span className="k-q"><kbd>Q</kbd> En duda</span>
        </div>
        <p className="v-lock">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="5" y="11" width="14" height="10" rx="1.5" />
            <path d="M8 11V8a4 4 0 0 1 8 0v3" />
          </svg>
          Etapa cerrada por el administrador
        </p>
      </div>
    </Pantalla>
  );
}

/* 04 · Catálogo ----------------------------------------------------------- */

const SUGERENCIAS: [string, string, number][] = [
  ["EST-12", "Concreto f’c 250 en trabes", 92],
  ["EST-14", "Concreto f’c 250 en columnas", 64],
  ["CIM-03", "Concreto f’c 200 en cimentación", 41],
];

export function VistaCatalogo() {
  return (
    <Pantalla nodo={3} titulo="Catálogo">
      <div className="v-cat">
        <div className="v-from">
          <span className="v-from-k">Del plano</span>
          <b>Trabe T-3 · concreto f’c 250</b>
          <span className="l68-mono">0.51 m³</span>
        </div>
        <p className="v-cat-h">Sugerencias de tu catálogo</p>
        <ul className="v-sug">
          {SUGERENCIAS.map(([clave, texto, score], n) => (
            <li key={clave} style={{ ...i(n), "--score": score / 100 } as CSSProperties} className={n === 0 ? "is-best" : undefined}>
              <span className="l68-mono">{clave}</span>
              <span>{texto}</span>
              <span className="v-score" aria-label={`Coincidencia ${score}%`}>
                <i />
                <span className="l68-mono">{score}%</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="v-adopt">
          <span className="v-adopt-btn">Adoptar EST-12</span>
          <span className="v-adopted">Adoptada · Klave la recuerda en tus próximas obras</span>
        </p>
        <ul className="v-prov">
          <li>
            <span>Concreto f’c 250</span>
            <span className="v-chip">Publicación oficial</span>
            <span className="v-chip is-ok">vigente</span>
          </li>
          <li>
            <span>Cimbra en trabes</span>
            <span className="v-chip">Cotización de tu proveedor</span>
            <span className="v-chip is-warn">por revisar</span>
          </li>
          <li>
            <span>Acero #4</span>
            <span className="v-chip is-gap">Sin precio</span>
            <span />
          </li>
        </ul>
      </div>
    </Pantalla>
  );
}

/* 05 · Presupuesto -------------------------------------------------------- */

export function VistaPresupuesto() {
  return (
    <Pantalla nodo={4} titulo="Presupuesto">
      <div className="v-budget">
        <div className="v-total">
          <span>Costo directo</span>
          <b className="l68-mono">
            $ <span data-cuenta="1284350" data-luego="1301742" data-luego-ms="3000" data-decimales="2">1,301,742.00</span>
          </b>
          <span className="v-delta l68-mono">▲ $ 17,392.00</span>
        </div>
        <div className="v-tiers">
          <span className="is-block">
            <b className="v-swap"><i>1</i><i>0</i></b> bloqueante
          </span>
          <span><b>2</b> dinero</span>
          <span><b>4</b> revisar</span>
        </div>
        <div className="v-finding">
          <p className="v-finding-t">
            <span className="v-tag">Bloqueante</span>
            3 conceptos cobran f’c 250; el plano pide f’c 300.
          </p>
          <div className="v-action">
            <p>
              <b>Acción propuesta:</b> adoptar el precio publicado para f’c 300 y corregir la
              descripción.
            </p>
            <p className="l68-mono v-fromto">f’c 250 → f’c 300 · reversible</p>
            <span className="v-apply">
              <i>Aplicar</i>
              <i>Aplicado</i>
            </span>
          </div>
        </div>
        <div className="v-export">
          <span className="v-export-lock">
            <i>Exportar bloqueado hasta resolver o dar un motivo</i>
            <i>Listo para exportar</i>
          </span>
          <span className="v-fmt">Excel con croquis</span>
          <span className="v-fmt">OPUS</span>
          <span className="v-fmt">Neodata</span>
        </div>
      </div>
    </Pantalla>
  );
}

/* 06 · Programa ----------------------------------------------------------- */

const PARTIDAS: [string, number, number, boolean?][] = [
  ["Preliminares", 0, 1],
  ["Cimentación", 1, 2.5],
  ["Castillos nivel 1", 3, 1.5],
  ["Trabes nivel 1", 3.8, 1.3, true],
  ["Losa nivel 1", 4.8, 1.6],
  ["Estructura nivel 2", 6.2, 2],
  ["Losa de azotea", 8, 1.6],
];

export function VistaPrograma() {
  return (
    <Pantalla nodo={5} titulo="Programa de obra">
      <div className="v-gantt" style={{ "--weeks": 10 } as CSSProperties}>
        <div className="v-weeks" aria-hidden="true">
          <span />
          <span className="v-week-row">
            {Array.from({ length: 10 }, (_, n) => (
              <i key={n}>S{n + 1}</i>
            ))}
          </span>
        </div>
        <ul>
          {PARTIDAS.map(([nombre, inicio, dura, traza], n) => (
            <li key={nombre} className={traza ? "is-traced" : undefined}>
              <span>{nombre}</span>
              <span className="v-lane">
                <i style={{ ...i(n), "--s": inicio, "--d": dura } as CSSProperties} />
              </span>
            </li>
          ))}
        </ul>
        <div className="v-flow">
          <span>Flujo de efectivo</span>
          <svg viewBox="0 0 400 90" preserveAspectRatio="none" aria-hidden="true">
            <path className="v-curve" pathLength={1} d="M0 86 C 70 84, 110 76, 160 58 S 260 14, 400 6" />
            <line className="v-est" x1="160" y1="0" x2="160" y2="90" />
            <line className="v-est" x1="320" y1="0" x2="320" y2="90" />
          </svg>
          <span className="v-est-labels">
            <i style={{ left: "40%" }}>
              E<span className="v-long">stimación </span>1
            </i>
            <i style={{ left: "80%" }}>
              E<span className="v-long">stimación </span>2
            </i>
          </span>
        </div>
      </div>
    </Pantalla>
  );
}

/* Equipo: presencia y cambios -------------------------------------------- */

const CAMBIOS: [string, string, string?][] = [
  ["Ana excluyó K-7", "duplicada en E-03", "▼ $ 3,120.00"],
  ["Luis adoptó EST-12", "de tu catálogo", "▲ $ 17,392.00"],
  ["Administración cerró Revisión", "la etapa queda bloqueada"],
  ["Versión 3 guardada", "frente a Rev B: 2 aditivas, 1 deductiva"],
];

export function VistaEquipo() {
  return (
    <figure className="l68-app is-team" data-play>
      <div className="l68-app-bar">
        <span className="l68-app-crumb">
          <span className="v-obra">
            Obra de ejemplo <span aria-hidden="true">/</span>{" "}
          </span>
          <b>Cambios</b>
        </span>
        <span className="v-people" aria-label="Ana en Revisión, Luis en Catálogo y tú en Presupuesto">
          <i title="Ana · Revisión">AR</i>
          <i title="Luis · Catálogo">LM</i>
          <i className="is-you" title="Tú · Presupuesto">TÚ</i>
        </span>
      </div>
      <div className="l68-app-body">
        <ol className="v-feed">
          {CAMBIOS.map(([quien, que, delta], n) => (
            <li key={quien} style={i(n)}>
              <b>{quien}</b>
              <span>{que}</span>
              {delta && <span className="l68-mono v-feed-d">{delta}</span>}
            </li>
          ))}
        </ol>
      </div>
      <figcaption>Pantalla ilustrativa: nombres y montos de ejemplo.</figcaption>
    </figure>
  );
}
