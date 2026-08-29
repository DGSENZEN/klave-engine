"use client";

import { useParams } from "next/navigation";
import { TableroBoard } from "@/components/Tablero";

export default function TableroPage() {
  const { id } = useParams<{ id: string }>();
  return <TableroBoard id={id} />;
}
