import type { Progreso } from "./tipos";

// Dónde se guarda el progreso: en la cuenta (servidor) cuando hay cuentas, y
// siempre también aquí, en el navegador, para que una base de usuarios caída
// no detenga el recorrido.

export type EstadoPaso = "hecho" | "saltado" | "no_encontrado";

export type AlmacenProgreso = {
  cargar(): Promise<Progreso>;
  guardar(pasoId: string, estado: EstadoPaso): Promise<void>;
  borrar(): Promise<void>;
};

type Local = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

const CLAVE = "klave.recorrido";

function leer(local: Local): Progreso {
  try {
    const crudo = local.getItem(CLAVE);
    const valor = crudo ? (JSON.parse(crudo) as unknown) : {};
    return valor && typeof valor === "object" ? (valor as Progreso) : {};
  } catch {
    return {};
  }
}

function escribir(local: Local, progreso: Progreso): void {
  try {
    local.setItem(CLAVE, JSON.stringify(progreso));
  } catch {
    // Sin almacenamiento (ventana privada): el recorrido sigue, sin memoria.
  }
}

export function crearAlmacen(remoto: AlmacenProgreso | null, local: Local): AlmacenProgreso {
  return {
    async cargar() {
      if (remoto) {
        try {
          const progreso = await remoto.cargar();
          escribir(local, progreso);
          return progreso;
        } catch {
          // cae a lo local
        }
      }
      return leer(local);
    },
    async guardar(pasoId, estado) {
      if (estado !== "no_encontrado") escribir(local, { ...leer(local), [pasoId]: estado });
      try {
        await remoto?.guardar(pasoId, estado);
      } catch {
        // lo local ya lo tiene
      }
    },
    async borrar() {
      try {
        local.removeItem(CLAVE);
      } catch {
        // nada que borrar
      }
      try {
        await remoto?.borrar();
      } catch {
        // el servidor lo borrará la próxima vez
      }
    },
  };
}
