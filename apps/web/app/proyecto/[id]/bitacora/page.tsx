"use client";

/**
 * Bitácora de obra: el medio oficial de comunicación entre las partes.
 *
 * No hay botón de editar ni de borrar en ninguna nota, y ésa es la pantalla.
 * Una bitácora que se puede corregir no prueba nada, porque cualquier cosa que
 * dijera pudo haberse escrito después. Cuando una nota salió mal se asienta
 * otra que la aclara y las dos se quedan a la vista, encadenadas: la
 * equivocada arriba, la aclaración abajo diciendo a cuál corrige.
 *
 * Las notas se leen en orden ascendente, como se escribieron, y no al revés
 * como un muro de mensajes. Una bitácora se lee de corrido para reconstruir qué
 * pasó; ponerla de nuevo a viejo es cómodo para revisar lo último y pésimo para
 * lo que realmente se usa.
 *
 * Cada nota lleva de qué lado habla. Residente por la contratante,
 * superintendente por el contratista: si sólo escribe uno, la bitácora está
 * sirviendo de diario y no de prueba, y eso la pantalla lo dice.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowBendUpLeft, NotePencil, Plus } from "@phosphor-icons/react";
import {
  asentarNota,
  getBitacora,
  type EstadoBitacora,
  type NotaBitacora,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  Input,
  PageHeader,
  SectionTitle,
  Skeleton,
} from "@/components/ui";

const PARTES = [
  { valor: "contratante", label: "Residente (contratante)" },
  { valor: "contratista", label: "Superintendente (contratista)" },
  { valor: "supervision", label: "Supervisión externa" },
] as const;

const TIPOS = [
  { valor: "ordinaria", label: "Ordinaria" },
  { valor: "extraordinaria", label: "Extraordinaria" },
  { valor: "cierre", label: "Cierre" },
] as const;

const TONO_PARTE: Record<string, "accent" | "success" | "default"> = {
  contratante: "accent",
  contratista: "success",
  supervision: "default",
};

function hoy() {
  return new Date().toISOString().slice(0, 10);
}

function Nota({
  nota,
  onAclarar,
}: {
  nota: NotaBitacora;
  onAclarar: (numero: number) => void;
}) {
  return (
    <div className="border-t border-border py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-sm tabular text-muted">
            Nota {nota.numero}
          </span>
          <Badge tone={TONO_PARTE[nota.parte] ?? "default"}>
            {PARTES.find((p) => p.valor === nota.parte)?.label ?? nota.parte}
          </Badge>
          {nota.tipo !== "ordinaria" && <Badge tone="warning">{nota.tipo}</Badge>}
          {nota.referencia !== null && (
            <span className="flex items-center gap-1 text-xs text-muted">
              <ArrowBendUpLeft size={12} /> aclara la nota {nota.referencia}
            </span>
          )}
        </div>
        <span className="text-xs text-muted">{nota.fecha}</span>
      </div>

      <p className="mt-2 whitespace-pre-wrap text-sm">{nota.texto}</p>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>
          {nota.autor}
          {nota.cargo ? ` · ${nota.cargo}` : ""}
        </span>
        <button
          type="button"
          onClick={() => onAclarar(nota.numero)}
          className="underline-offset-2 hover:text-foreground hover:underline"
        >
          Aclarar esta nota
        </button>
      </div>
    </div>
  );
}

export default function BitacoraPage() {
  const { id } = useParams<{ id: string }>();
  const [notas, setNotas] = useState<NotaBitacora[]>([]);
  const [estado, setEstado] = useState<EstadoBitacora | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [borrador, setBorrador] = useState<NotaBitacora | null>(null);

  const leer = useCallback(async () => {
    const r = await getBitacora(id);
    setNotas(r.notas);
    setEstado(r.estado);
    return r.estado;
  }, [id]);

  useEffect(() => {
    let vivo = true;
    getBitacora(id)
      .then((r) => {
        if (!vivo) return;
        setNotas(r.notas);
        setEstado(r.estado);
      })
      .catch(() => vivo && setError("No se pudo leer la bitácora."))
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, [id]);

  function nueva(referencia: number | null = null) {
    if (!estado) return;
    setError(null);
    setBorrador({
      numero: estado.siguiente_numero,
      fecha: hoy(),
      tipo: estado.abierta ? "ordinaria" : "apertura",
      parte: "contratante",
      autor: "",
      cargo: "",
      texto: "",
      referencia,
      asentada_en: "",
    });
  }

  async function asentar() {
    if (!borrador) return;
    setError(null);
    try {
      await asentarNota(id, borrador, getBrowserActor());
      setBorrador(null);
      await leer();
    } catch (err) {
      const detalle = (err as { detail?: { message?: string } })?.detail?.message;
      setError(detalle ?? "No se pudo asentar la nota.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Bitácora de obra"
        sub="El medio oficial de comunicación entre las partes (RLOPSRM art. 123). Lo que se asienta obliga; lo que no se asentó no pasó."
        actions={
          !estado?.cerrada && (
            <Button onClick={() => nueva()} disabled={!estado || !!borrador}>
              <Plus size={16} />
              {estado?.abierta ? "Asentar nota" : "Abrir la bitácora"}
            </Button>
          )
        }
      />

      {error && <Callout tone="danger">{error}</Callout>}
      {estado?.avisos.map((a) => (
        <Callout key={a} tone="warning">
          {a}
        </Callout>
      ))}
      {cargando && <Skeleton className="h-32 w-full" />}

      {borrador && (
        <Card className="p-5">
          <SectionTitle
            sub={
              borrador.referencia !== null
                ? `Aclara la nota ${borrador.referencia}, que se queda asentada tal como está: así es como una bitácora prueba algo.`
                : "Una vez asentada no se edita. Si sale mal, se aclara con otra nota."
            }
          >
            {borrador.tipo === "apertura"
              ? "Nota de apertura"
              : `Nota ${borrador.numero}`}
          </SectionTitle>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block">
              <span className="microlabel">Fecha del hecho</span>
              <Input
                type="date"
                className="mt-1 w-full"
                value={borrador.fecha}
                onChange={(e) => setBorrador({ ...borrador, fecha: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="microlabel">Quién asienta</span>
              <select
                className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-ring"
                value={borrador.parte}
                onChange={(e) =>
                  setBorrador({
                    ...borrador,
                    parte: e.target.value as NotaBitacora["parte"],
                  })
                }
              >
                {PARTES.map((p) => (
                  <option key={p.valor} value={p.valor}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="microlabel">Nombre</span>
              <Input
                className="mt-1 w-full"
                placeholder="Ing. Nombre Apellido"
                value={borrador.autor}
                onChange={(e) => setBorrador({ ...borrador, autor: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="microlabel">Cargo</span>
              <Input
                className="mt-1 w-full"
                placeholder="Residente de obra"
                value={borrador.cargo}
                onChange={(e) => setBorrador({ ...borrador, cargo: e.target.value })}
              />
            </label>
          </div>

          {borrador.tipo !== "apertura" && (
            <label className="mt-3 block max-w-xs">
              <span className="microlabel">Tipo de nota</span>
              <select
                className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-ring"
                value={borrador.tipo}
                onChange={(e) =>
                  setBorrador({
                    ...borrador,
                    tipo: e.target.value as NotaBitacora["tipo"],
                  })
                }
              >
                {TIPOS.map((t) => (
                  <option key={t.valor} value={t.valor}>
                    {t.label}
                  </option>
                ))}
              </select>
              {borrador.tipo === "cierre" && (
                <span className="mt-1 block text-xs text-warning">
                  Después de la nota de cierre no se asienta nada más. Lo que quede
                  pendiente va en el finiquito.
                </span>
              )}
            </label>
          )}

          <label className="mt-4 block">
            <span className="microlabel">Texto de la nota</span>
            <textarea
              rows={5}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm placeholder:text-faint focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder={
                borrador.tipo === "apertura"
                  ? "Datos del contrato, partes que intervienen, fecha de inicio y plazo."
                  : "Qué pasó, dónde, y qué se pide o se resuelve."
              }
              value={borrador.texto}
              onChange={(e) => setBorrador({ ...borrador, texto: e.target.value })}
            />
          </label>

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setBorrador(null)}>
              Cancelar
            </Button>
            <Button onClick={() => void asentar()}>Asentar nota</Button>
          </div>
        </Card>
      )}

      {!cargando && notas.length === 0 && !borrador && (
        <EmptyState
          icon={<NotePencil size={28} />}
          title="La bitácora no está abierta"
          hint="Su primera nota es la de apertura, con los datos del contrato (RLOPSRM art. 125)."
          action={<Button onClick={() => nueva()}>Abrir la bitácora</Button>}
        />
      )}

      {notas.length > 0 && (
        <Card className="p-5">
          <SectionTitle sub="En el orden en que se escribieron. Ninguna nota se edita ni se quita: una que salió mal se aclara con otra, y las dos se quedan.">
            {notas.length} {notas.length === 1 ? "nota asentada" : "notas asentadas"}
          </SectionTitle>
          <div className="mt-2">
            {notas.map((n) => (
              <Nota key={n.numero} nota={n} onAclarar={(numero) => nueva(numero)} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
