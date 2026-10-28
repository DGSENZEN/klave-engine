import type { Metadata } from "next";
import Link from "next/link";
import localFont from "next/font/local";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Emblema68 } from "@/components/portada/Emblema68";
import { MarcaKlave } from "@/components/portada/MarcaKlave";
import { RutaPortada } from "@/components/portada/RutaPortada";
import {
  VistaCatalogo,
  VistaEquipo,
  VistaPlanos,
  VistaPresupuesto,
  VistaPrograma,
  VistaRevision,
  VistaVisor,
} from "@/components/portada/Vistas";
import "./portada.css";

const archivo = localFont({
  src: "../fonts/Archivo.woff2",
  variable: "--font-archivo",
  weight: "100 900",
  declarations: [{ prop: "font-stretch", value: "62% 125%" }],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Generadores de obra a partir de tus planos",
  description:
    "Klave lee planos estructurales DWG/DXF y entrega generadores de obra negra con la evidencia de cada cantidad, listos para OPUS y Neodata.",
};

const dos = (n: number) => String(n).padStart(2, "0");

export default function PortadaPage() {
  return (
    <div className={`l68 ${archivo.variable}`}>
      <div className="l68-wrap">
        <header className="l68-nav">
          <Link href="/portada" className="l68-word" aria-label="Klave, portada">
            Klave
          </Link>
          <nav aria-label="Principal">
            <ul>
              <li className="l68-hide-sm">
                <Link href="/como-funciona" className="l68-link">
                  Cómo funciona
                </Link>
              </li>
              <li className="l68-hide-sm">
                <Link href="/glosario" className="l68-link">
                  Glosario
                </Link>
              </li>
              <li>
                <Link href="/bienvenida" className="l68-link">
                  Entrar
                </Link>
              </li>
              <li>
                <Link href="/registro" className="l68-btn l68-btn--accent l68-btn--sm">
                  Crear cuenta
                </Link>
              </li>
              <li className="l68-hide-sm">
                <ThemeToggle />
              </li>
            </ul>
          </nav>
        </header>

        <main>
          <section className="l68-hero" aria-labelledby="portada-titulo">
            <Emblema68 />
            <h1 id="portada-titulo">Del plano al generador, sin inventar nada.</h1>
            <p className="l68-lede">
              Klave lee tus planos estructurales y arma los generadores de obra negra. Cada cantidad
              dice de qué eje, de qué hoja y con qué medida salió, y llega a OPUS o Neodata con tus
              propias claves.
            </p>
            <div className="l68-actions">
              <Link href="/registro" className="l68-btn l68-btn--accent">
                Crear cuenta <ArrowRight size={18} weight="bold" aria-hidden="true" />
              </Link>
              <Link href="/bienvenida" className="l68-btn l68-btn--line">
                Entrar
              </Link>
              <p className="l68-note">El administrador de tu taller aprueba cada cuenta nueva.</p>
            </div>
          </section>

          <RutaPortada>
            <Estacion
              n={1}
              nombre="Planos"
              texto="Sube el juego completo tal como sale del despacho. Klave convierte el DWG, revisa unidades y capas, y separa lo que se lee a fondo de lo que solo se cuenta."
              rasgos={[
                "Conversión de DWG automática",
                "Lectura del plano: unidades, capas, bloques y advertencias",
                "Otras disciplinas como levantamiento; el fondo arquitectónico no se cobra",
              ]}
            >
              <VistaPlanos />
            </Estacion>

            <Estacion
              n={2}
              nombre="Disciplinas"
              texto="Detectores deterministas leen ejes, zapatas, castillos, trabes y losas con las convenciones que ya usas. Selecciona cualquier elemento y ves de dónde salió."
              rasgos={[
                "Secciones tomadas de cuadros, detalles y cotas",
                "Herramienta de medición en el visor",
                "Si hay IA, solo sugiere: su lectura queda «por confirmar»",
              ]}
            >
              <VistaVisor />
            </Estacion>

            <Estacion
              n={3}
              nombre="Revisión"
              texto="Tu equipo confirma, excluye o deja en duda cada detección sin soltar el teclado. Cada exclusión lleva su motivo y cada etapa se cierra con nombre."
              rasgos={[
                "C, X y Q en el visor; revisión por lote en obras grandes",
                "Lo que el dibujo no trae se agrega a mano, con su medida",
                "El administrador cierra cada etapa del tablero",
              ]}
            >
              <VistaRevision />
            </Estacion>

            <Estacion
              n={4}
              nombre="Catálogo"
              texto="Cada concepto leído llega a tus claves. Klave sugiere las más parecidas, tú adoptas una y la recuerda en la siguiente obra."
              rasgos={[
                "Importa tu catálogo, precios y matrices de OPUS o Neodata",
                "Cada precio dice de dónde viene y si sigue vigente",
                "Lo que no tiene precio queda a la vista, nunca como $0",
              ]}
            >
              <VistaCatalogo />
            </Estacion>

            <Estacion
              n={5}
              nombre="Presupuesto"
              texto="El presupuesto separa lo que puede costar dinero de lo que no. Los hallazgos llegan por gravedad y el copiloto propone cada corrección con vista previa."
              rasgos={[
                "Hallazgos bloqueantes, de dinero y por revisar",
                "Un bloqueante detiene la exportación hasta resolverlo o dar un motivo",
                "Generadores en Excel con croquis, o listos para OPUS y Neodata",
              ]}
            >
              <VistaPresupuesto />
            </Estacion>

            <Estacion
              n={6}
              nombre="Programa"
              texto="La misma obra sigue a programa, flujo de efectivo y estimaciones. Las duraciones salen del rendimiento de cada matriz, no de una tabla aparte."
              rasgos={[
                "Rendimientos conforme al RLOPSRM",
                "Flujo de efectivo y estimaciones sobre el mismo catálogo",
                "Convenios, bitácora y finiquito en la misma obra",
              ]}
            >
              <VistaPrograma />
            </Estacion>

            <section className="l68-station l68-team" aria-labelledby="portada-equipo">
              <VistaEquipo />
              <div className="l68-station-text">
                <h2 id="portada-equipo">Tu equipo, en la misma obra.</h2>
                <p>
                  Todos trabajan sobre la misma obra al mismo tiempo: ves quién está en qué etapa,
                  qué cambió y cuánto movió el total.
                </p>
                <Rasgos
                  items={[
                    "Presencia y cambios al instante, con el monto que movieron",
                    "Versiones guardadas y diferencias entre revisiones del plano",
                    "Un recorrido guiado con una obra de ejemplo, en la pantalla real",
                  ]}
                />
              </div>
            </section>

            <section className="l68-refuse" aria-labelledby="portada-no">
              <h2 id="portada-no">Lo que Klave se niega a hacer.</h2>
              <ul>
                <Negativa no="Inventar una cantidad.">
                  Toda cantidad apunta a un trazo del dibujo o a un supuesto escrito junto al número.
                </Negativa>
                <Negativa no="Poner $0 donde falta un precio.">
                  Un concepto sin precio se queda como hueco visible, y un total incompleto dice qué
                  le falta.
                </Negativa>
                <Negativa no="Mostrar dinero sin unidades confiables.">
                  Un plano sin unidades claras sale marcado SIN UNIDADES y sin precios.
                </Negativa>
                <Negativa no="Dejar que la IA decida.">
                  La IA sugiere y su lectura queda «por confirmar». La firma es de tu equipo.
                </Negativa>
              </ul>
            </section>

            <section className="l68-practice" aria-labelledby="portada-practica">
              <h2 id="portada-practica">Habla como tu oficina.</h2>
              <ul>
                <li>Ejes, trabes, castillos y zapatas, con sus marcas.</li>
                <li>Salario real y costo horario conforme al RLOPSRM.</li>
                <li>Precios de referencia de CDMX, SICT, CONAGUA, Chiapas y Guanajuato.</li>
                <li>Importa y exporta OPUS y Neodata. Tu cierre no cambia.</li>
              </ul>
            </section>

            <section className="l68-end" aria-labelledby="portada-fin">
              <span className="l68-ring" aria-hidden="true" />
              <h2 id="portada-fin">Abre la cuenta de tu taller.</h2>
              <p className="l68-lede" style={{ marginTop: 20 }}>
                Crea tu cuenta y el administrador de tu taller la aprueba. Si ya tienes una, entra.
              </p>
              <div className="l68-actions">
                <Link href="/registro" className="l68-btn l68-btn--accent">
                  Crear cuenta <ArrowRight size={18} weight="bold" aria-hidden="true" />
                </Link>
                <Link href="/bienvenida" className="l68-btn l68-btn--line">
                  Entrar
                </Link>
              </div>
            </section>
          </RutaPortada>

          <MarcaKlave />
        </main>

        <footer className="l68-foot">
          <span>Klave · Ingeniería de costos a partir de planos estructurales.</span>
          <ul>
            <li><Link href="/como-funciona">Cómo funciona</Link></li>
            <li><Link href="/glosario">Glosario</Link></li>
            <li><Link href="/bienvenida">Entrar</Link></li>
          </ul>
        </footer>
        <div style={{ height: 40 }} />
      </div>
    </div>
  );
}

function Estacion({
  n,
  nombre,
  texto,
  rasgos,
  children,
}: {
  n: number;
  nombre: string;
  texto: string;
  rasgos: string[];
  children: React.ReactNode;
}) {
  return (
    <section data-estacion={dos(n)} className="l68-station" aria-labelledby={`estacion-${n}-t`}>
      <span className="l68-ring" aria-hidden="true" />
      {children}
      <div className="l68-station-text">
        <span className="l68-num l68-mono">{dos(n)}</span>
        <h2 id={`estacion-${n}-t`} className="l68-stage-title">
          {nombre}
        </h2>
        <p>{texto}</p>
        <Rasgos items={rasgos} />
      </div>
    </section>
  );
}

function Rasgos({ items }: { items: string[] }) {
  return (
    <ul className="l68-feats">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Negativa({ no, children }: { no: string; children: React.ReactNode }) {
  return (
    <li>
      <div>
        <s>
          <span className="sr-only">Nunca: </span>
          {no}
        </s>
      </div>
      <p>{children}</p>
    </li>
  );
}
