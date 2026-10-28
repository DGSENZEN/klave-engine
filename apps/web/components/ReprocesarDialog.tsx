"use client";

import { ConfirmDialog } from "@/components/ConfirmDialog";

/** Reprocesar vuelve a leer los planos para todos los que tienen el proyecto
 * abierto: es una acción de autoridad y se dice antes, igual en todas partes. */
export function ReprocesarDialog({
  open,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <ConfirmDialog
      open={open}
      title="Reprocesar el proyecto — vuelve a leer los planos para todos los que lo tienen abierto"
      description="Sus pantallas siguen a la vista con la lectura anterior y se actualizan al terminar. Las revisiones y los ajustes se conservan."
      confirmLabel="Reprocesar"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
