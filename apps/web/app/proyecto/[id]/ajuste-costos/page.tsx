"use client";

/**
 * Ajuste de costos: cuando los insumos suben y el contrato sigue diciendo lo
 * mismo.
 *
 * La pantalla está construida alrededor de un hueco: el índice. El factor sale
 * de índices del INPP que publica el INEGI, y esta aplicación no guarda
 * ninguno ni lo va a estimar. Mientras no estén los dos valores no hay factor,
 * y lo que se enseña es la petición del dato — con el nombre de la publicación
 * al lado, porque en una revisión hay que poder ir a comprobarlo.
 *
 * Es tentador poner ahí un número «de referencia» para que la pantalla se vea
 * completa. Un ajuste de costos con índices inventados no es un cálculo
 * optimista: es un cobro sin sustento, y se detecta a la primera.
 *
 * Lo demás sí se precarga, porque la aplicación ya lo sabe: lo contratado sale
 * del catálogo con sus convenios y lo ejecutado de las estimaciones. Volver a
 * teclearlo es donde se cuelan las cantidades que no cuadran con lo cobrado.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ChartLineUp, Plus, Trash } from "@phosphor-icons/react";
import {
  borrarAjuste,
  getAjustes,
  guardarAjuste,
  money,
  prepararAjuste,
  type AjusteConResumen,
  type ResumenAjuste,
  type SolicitudAjuste,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  Input,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
} from "@/components/ui";

/** El factor, o el hueco que impide calcularlo. */
function Factor({ resumen }: { resumen: ResumenAjuste }) {
  if (!resumen.calculable) {
    return (
      <Metric
        label="Factor de ajuste"
        value="sin índice"
        hint="Captura los dos valores publicados y el factor sale solo."
        icon={<ChartLineUp size={18} />}
      />
    );
  }
  const sube = (resumen.factor ?? 1) >= 1;
  return (
    <Metric
      label="Factor de ajuste"
      value={resumen.factor?.toFixed(4) ?? "—"}
      accent={sube ? "accent" : "success"}
      hint={`${resumen.indice_base} → ${resumen.indice_ajuste} · ${
        sube ? "a favor del contratista" : "a favor de la contratante"
      }`}
      icon={<ChartLineUp size={18} />}
    />
  );
}

function EditorAjuste({
  solicitud,
  resumen,
  onGuardar,
  onCancelar,
}: {
  solicitud: SolicitudAjuste;
  resumen: ResumenAjuste;
  onGuardar: (s: SolicitudAjuste) => void;
  onCancelar: () => void;
}) {
  const [local, setLocal] = useState<SolicitudAjuste>(solicitud);
  const indice = local.indice ?? {
    nombre: "",
    fuente: "INEGI",
    publicacion: "",
    valores: {},
  };

  function setIndice(campo: string, valor: string) {
    setLocal({ ...local, indice: { ...indice, [campo]: valor } });
  }

  function setValor(periodo: string, valor: string) {
    const valores = { ...indice.valores };
    if (valor.trim() === "") delete valores[periodo];
    else valores[periodo] = Number(valor);
    setLocal({ ...local, indice: { ...indice, valores } });
  }

  const pendiente = local.renglones.reduce(
    (s, r) => s + Math.max(r.quantity_contract - r.quantity_executed, 0) * r.unit_price,
    0,
  );

  return (
    <Card className="p-5">
      <SectionTitle sub="El ajuste aplica a la obra pendiente a la fecha del incremento. Lo ya estimado se pagó a los precios de entonces (RLOPSRM art. 173).">
        Solicitud de ajuste {local.numero}
      </SectionTitle>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="microlabel">Periodo base</span>
          <Input
            className="mt-1 w-full"
            placeholder="2026-01"
            value={local.periodo_base}
            onChange={(e) => setLocal({ ...local, periodo_base: e.target.value })}
          />
          <span className="mt-1 block text-xs text-muted">
            Del acto de presentación y apertura de proposiciones — no de la firma del
            contrato ni del arranque de la obra.
          </span>
        </label>
        <label className="block">
          <span className="microlabel">Periodo del ajuste</span>
          <Input
            className="mt-1 w-full"
            placeholder="2026-07"
            value={local.periodo_ajuste}
            onChange={(e) => setLocal({ ...local, periodo_ajuste: e.target.value })}
          />
        </label>
      </div>

      <div className="mt-5 rounded-lg border border-border bg-surface-2/40 p-4">
        <div className="microlabel">Índice de precios</div>
        <p className="mt-1 text-xs text-muted">
          Klave no guarda índices ni los estima. Captura los dos valores de la publicación
          que vas a citar: un ajuste con índices inventados es un cobro sin sustento.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="microlabel">Nombre del índice</span>
            <Input
              className="mt-1 w-full"
              placeholder="INPP construcción de edificaciones"
              value={indice.nombre}
              onChange={(e) => setIndice("nombre", e.target.value)}
            />
          </label>
          <label className="block">
            <span className="microlabel">Publicación</span>
            <Input
              className="mt-1 w-full"
              placeholder="INEGI, INPP, cuadro y fecha"
              value={indice.publicacion}
              onChange={(e) => setIndice("publicacion", e.target.value)}
            />
          </label>
          <label className="block">
            <span className="microlabel">
              Valor en {local.periodo_base || "el periodo base"}
            </span>
            <Input
              type="number"
              step="any"
              className="mt-1 w-full text-right tabular-nums"
              value={indice.valores[local.periodo_base] ?? ""}
              onChange={(e) => setValor(local.periodo_base, e.target.value)}
              disabled={!local.periodo_base}
            />
          </label>
          <label className="block">
            <span className="microlabel">
              Valor en {local.periodo_ajuste || "el periodo del ajuste"}
            </span>
            <Input
              type="number"
              step="any"
              className="mt-1 w-full text-right tabular-nums"
              value={indice.valores[local.periodo_ajuste] ?? ""}
              onChange={(e) => setValor(local.periodo_ajuste, e.target.value)}
              disabled={!local.periodo_ajuste}
            />
          </label>
        </div>
      </div>

      <label className="mt-4 flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={local.atraso_imputable_al_contratista}
          onChange={(e) =>
            setLocal({ ...local, atraso_imputable_al_contratista: e.target.checked })
          }
        />
        <span>
          El atraso es imputable al contratista
          <span className="block text-xs text-muted">
            Su obra atrasada se ajusta con los índices que le tocaban según el programa, no
            con los de este periodo (RLOPSRM art. 176). De otro modo atrasarse pagaría.
          </span>
        </span>
      </label>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted">
          {local.renglones.length}{" "}
          {local.renglones.length === 1 ? "concepto" : "conceptos"} ·{" "}
          <span className="font-medium text-foreground">{money(pendiente)}</span> pendientes
          de ejecutar
          {resumen.calculable && (
            <>
              {" "}
              · ajuste{" "}
              <span className="font-medium text-foreground">
                {money(resumen.importe_ajuste)}
              </span>
            </>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onCancelar}>
            Cancelar
          </Button>
          <Button onClick={() => onGuardar(local)}>Guardar solicitud</Button>
        </div>
      </div>
    </Card>
  );
}

export default function AjusteCostosPage() {
  const { id } = useParams<{ id: string }>();
  const [lista, setLista] = useState<AjusteConResumen[]>([]);
  const [editando, setEditando] = useState<AjusteConResumen | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmar, setConfirmar] = useState<number | null>(null);

  const leer = useCallback(async () => {
    const r = await getAjustes(id);
    setLista(r.ajustes);
  }, [id]);

  useEffect(() => {
    let vivo = true;
    getAjustes(id)
      .then((r) => vivo && setLista(r.ajustes))
      .catch(() => vivo && setError("No se pudieron leer las solicitudes de ajuste."))
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, [id]);

  async function nueva() {
    setError(null);
    try {
      setEditando(await prepararAjuste(id));
    } catch {
      setError("No se pudo preparar la solicitud.");
    }
  }

  async function guardar(sol: SolicitudAjuste) {
    await guardarAjuste(id, sol.numero, sol, getBrowserActor());
    setEditando(null);
    await leer();
  }

  async function eliminar(numero: number) {
    await borrarAjuste(id, numero, getBrowserActor());
    setConfirmar(null);
    await leer();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ajuste de costos"
        sub="Lo que subieron los insumos sobre la obra que falta por ejecutar (LOPSRM art. 57–58)."
        actions={
          <Button onClick={() => void nueva()}>
            <Plus size={16} /> Nueva solicitud
          </Button>
        }
      />

      {error && <Callout tone="danger">{error}</Callout>}
      {cargando && <Skeleton className="h-28 w-full" />}

      {editando && (
        <EditorAjuste
          key={editando.solicitud.numero}
          solicitud={editando.solicitud}
          resumen={editando.resumen}
          onGuardar={(s) => void guardar(s)}
          onCancelar={() => setEditando(null)}
        />
      )}

      {!cargando && lista.length === 0 && !editando && (
        <EmptyState
          icon={<ChartLineUp size={28} />}
          title="Sin solicitudes de ajuste"
          hint="Una solicitud se prepara con lo que falta por ejecutar; los índices los traes de la publicación del INEGI."
        />
      )}

      {lista.map(({ solicitud, resumen }) => (
        <Card key={solicitud.numero} className="p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <SectionTitle>
                Solicitud {solicitud.numero}
                {resumen.calculable ? (
                  <Badge tone={resumen.importe_ajuste >= 0 ? "accent" : "success"}>
                    {money(resumen.importe_ajuste)}
                  </Badge>
                ) : (
                  <Badge tone="warning">falta el índice</Badge>
                )}
              </SectionTitle>
              <div className="mt-1 text-sm text-muted">
                {solicitud.periodo_base || "—"} → {solicitud.periodo_ajuste || "—"}
                {solicitud.indice?.publicacion ? ` · ${solicitud.indice.publicacion}` : ""}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                onClick={() => setEditando({ solicitud, resumen })}
              >
                Editar
              </Button>
              {confirmar === solicitud.numero ? (
                <>
                  <span className="text-xs text-muted">¿Quitarla?</span>
                  <Button variant="ghost" onClick={() => setConfirmar(null)}>
                    No
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void eliminar(solicitud.numero)}
                  >
                    Sí, quitar
                  </Button>
                </>
              ) : (
                <Button variant="ghost" onClick={() => setConfirmar(solicitud.numero)}>
                  <Trash size={16} />
                </Button>
              )}
            </div>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <Factor resumen={resumen} />
            <Metric
              label="Pendiente de ejecutar"
              value={money(resumen.importe_pendiente)}
              hint={`${solicitud.renglones.length} ${
                solicitud.renglones.length === 1 ? "concepto" : "conceptos"
              } del contrato.`}
            />
            <Metric
              label="Base ajustable"
              value={money(resumen.importe_ajustable)}
              hint={
                resumen.importe_ajustable < resumen.importe_pendiente
                  ? "Descontada la obra atrasada por causa propia."
                  : "Toda la obra pendiente entra al ajuste."
              }
            />
          </div>

          {resumen.avisos.map((a) => (
            <Callout key={a} tone={resumen.calculable ? "info" : "warning"}>
              {a}
            </Callout>
          ))}
        </Card>
      ))}
    </div>
  );
}
