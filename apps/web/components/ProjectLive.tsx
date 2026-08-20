"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import {
  actorLabel,
  getBrowserActor,
  getBrowserClientId,
  parseHelloPresence,
  parsePresence,
  parseProjectEvent,
  projectEventsUrl,
  setBrowserActor,
} from "@/lib/collab";
import {
  getEventsHistory,
  money,
  publishActivity,
  publishPresence,
  type PresenceViewer,
  type ProjectEvent,
} from "@/lib/api";

type LiveToast = {
  id: number;
  message: string;
};

type LiveActivity = {
  id: number;
  actor: string;
  clientId: string | null;
  message: string;
  locationPath: string;
  locationLabel: string;
};

/** A committed data change, kept in a scrollable timeline (not just a toast). */
export type ChangeEntry = {
  id: number;
  ts: string;
  actor: string;
  isOwn: boolean;
  title: string;
  detail?: string;
};

const MAX_VISIBLE_TOASTS = 3;
const MAX_TIMELINE = 40;

type ProjectLiveValue = {
  latestEvent: ProjectEvent | null;
  actorName: string;
  setActorName: (value: string) => void;
  connected: boolean;
  /** Increments on every SSE hello. Reconnects can skip events the history
   * window no longer holds, so pages refetch when this changes. */
  connectionEpoch: number;
  clientId: string | null;
  viewers: PresenceViewer[];
  activities: LiveActivity[];
  sendActivity: (action: string, label?: string) => void;
  toasts: LiveToast[];
  dismissToast: (id: number) => void;
  timeline: ChangeEntry[];
  clearTimeline: () => void;
};

const ProjectLiveContext = createContext<ProjectLiveValue | null>(null);

export function ProjectLiveProvider({
  projectId,
  children,
}: {
  projectId: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [actorName, setActorNameState] = useState("Colaborador");
  const [clientId, setClientId] = useState<string | null>(null);
  const [latestEvent, setLatestEvent] = useState<ProjectEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectionEpoch, setConnectionEpoch] = useState(0);
  const [viewers, setViewers] = useState<PresenceViewer[]>([]);
  const [activities, setActivities] = useState<LiveActivity[]>([]);
  const [toasts, setToasts] = useState<LiveToast[]>([]);
  const [timeline, setTimeline] = useState<ChangeEntry[]>([]);
  const locationLabel = useMemo(
    () => projectLocationLabel(projectId, pathname),
    [pathname, projectId],
  );
  // The stream connects once per project/identity; navigation inside the
  // project reports the new location over HTTP instead of reconnecting. The
  // ref lets the connect effect read the current location without depending
  // on it (which would tear the stream down on every navigation).
  const locationRef = useRef({ path: pathname, label: locationLabel });
  useEffect(() => {
    locationRef.current = { path: pathname, label: locationLabel };
  }, [pathname, locationLabel]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setActorNameState(getBrowserActor());
      setClientId(getBrowserClientId());
    }, 0);
    return () => window.clearTimeout(handle);
  }, []);

  useEffect(() => {
    if (!clientId) return;
    const source = new EventSource(
      projectEventsUrl(
        projectId,
        actorName,
        clientId,
        locationRef.current.path,
        locationRef.current.label,
      ),
    );
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("hello", (message) => {
      setConnected(true);
      setConnectionEpoch((epoch) => epoch + 1);
      setViewers(parseHelloPresence(message as MessageEvent));
      // Rebuild the change timeline from server history on every (re)connect:
      // an event-sourced timeline with no history would permanently miss other
      // users' changes made before this tab connected or during a gap, and a
      // server restart resets sequence numbers, so replacing (not merging) is
      // the self-healing choice. Live events keep appending via onmessage.
      void getEventsHistory(projectId)
        .then((events) => {
          const entries: ChangeEntry[] = [];
          for (const event of events) {
            const entry = changeEntry(event, isOwnEvent(event, actorName, clientId));
            if (entry) entries.push(entry);
          }
          entries.reverse();
          setTimeline(entries.slice(0, MAX_TIMELINE));
        })
        .catch(() => {});
    });
    const pushToast = (id: number, message: string) => {
      // Cap the stack so a burst of edits can't grow a tall wall of toasts —
      // the full history lives in the timeline panel instead.
      setToasts((current) =>
        [...current.filter((toast) => toast.id !== id), { id, message }].slice(
          -MAX_VISIBLE_TOASTS,
        ),
      );
      window.setTimeout(() => {
        setToasts((current) => current.filter((toast) => toast.id !== id));
      }, 4500);
    };
    source.onmessage = (message) => {
      const event = parseProjectEvent(message);
      if (!event) return;
      if (event.type === "presence_updated") {
        setViewers(parsePresence(event.data.viewers));
        return;
      }
      if (event.type === "collaborator_activity") {
        const activity = liveActivity(event, clientId, actorName);
        if (activity) {
          setActivities((current) => [
            activity,
            ...current.filter(
              (item) => !activity.clientId || item.clientId !== activity.clientId,
            ),
          ].slice(0, 5));
          pushToast(event.seq, activity.message);
          window.setTimeout(() => {
            setActivities((current) => current.filter((item) => item.id !== event.seq));
          }, 9000);
        }
        return;
      }
      setLatestEvent(event);
      const own = isOwnEvent(event, actorName, clientId);
      const entry = changeEntry(event, own);
      if (entry) {
        setTimeline((current) =>
          [entry, ...current.filter((item) => item.id !== entry.id)].slice(0, MAX_TIMELINE),
        );
      }
      if (!own) {
        const messageText = toastMessage(event);
        if (messageText) pushToast(event.seq, messageText);
      }
    };
    return () => {
      source.close();
    };
    // locationRef keeps pathname/locationLabel out of these deps on purpose.
  }, [actorName, clientId, projectId]);

  useEffect(() => {
    if (!clientId || !connected) return;
    void publishPresence(
      projectId,
      { client_id: clientId, location_path: pathname, location_label: locationLabel },
      actorName,
    ).catch(() => {});
  }, [actorName, clientId, connected, locationLabel, pathname, projectId]);

  const sendActivity = useCallback(
    (action: string, label?: string) => {
      if (!clientId) return;
      void publishActivity(
        projectId,
        {
          client_id: clientId,
          action,
          label,
          location_path: pathname,
          location_label: locationLabel,
        },
        actorName,
      ).catch(() => {});
    },
    [actorName, clientId, locationLabel, pathname, projectId],
  );

  const value = useMemo<ProjectLiveValue>(
    () => ({
      latestEvent,
      actorName,
      connected,
      connectionEpoch,
      clientId,
      viewers,
      activities,
      sendActivity,
      toasts,
      dismissToast: (id) =>
        setToasts((current) => current.filter((toast) => toast.id !== id)),
      timeline,
      clearTimeline: () => setTimeline([]),
      setActorName: (next) => setActorNameState(setBrowserActor(next)),
    }),
    [
      activities,
      actorName,
      clientId,
      connected,
      connectionEpoch,
      latestEvent,
      sendActivity,
      timeline,
      toasts,
      viewers,
    ],
  );

  return <ProjectLiveContext.Provider value={value}>{children}</ProjectLiveContext.Provider>;
}

export function useProjectLive(): ProjectLiveValue {
  const value = useContext(ProjectLiveContext);
  if (value) return value;
  return {
    latestEvent: null,
    actorName: "Colaborador",
    connected: false,
    connectionEpoch: 0,
    clientId: null,
    viewers: [],
    activities: [],
    sendActivity: () => {},
    toasts: [],
    dismissToast: () => {},
    timeline: [],
    clearTimeline: () => {},
    setActorName: () => {},
  };
}

function toastMessage(event: ProjectEvent): string | null {
  const actor = actorLabel(event.actor);
  switch (event.type) {
    case "costing_updated":
      return `${actor} recalculó los costos`;
    case "project_updated":
      return `${actor} actualizó el proyecto`;
    case "run_published":
      return "Se publicó un nuevo procesamiento";
    case "catalog_updated":
      return `${actor} actualizó el catálogo del taller`;
    default:
      return null;
  }
}

/** Turn a committed-change event into a timeline row with "what and how". */
function changeEntry(event: ProjectEvent, isOwn: boolean): ChangeEntry | null {
  const actor = isOwn ? "Tú" : actorLabel(event.actor);
  const base = { id: event.seq, ts: event.ts, actor, isOwn };
  switch (event.type) {
    case "costing_updated": {
      const grand = dataNumber(event, "grand_total");
      const prev = dataNumber(event, "prev_grand_total");
      let detail = grand != null ? `Total ${money(grand)}` : undefined;
      if (detail && grand != null && prev != null && Math.abs(grand - prev) > 0.5) {
        const delta = grand - prev;
        detail += ` · ${delta > 0 ? "▲" : "▼"} ${money(Math.abs(delta))}`;
      }
      return { ...base, title: `${actor} recalculó los costos`, detail };
    }
    case "run_published":
      return {
        ...base,
        title: "Nuevo procesamiento publicado",
        detail: "Detección y presupuesto actualizados",
      };
    case "project_updated":
      return { ...base, title: `${actor} actualizó el proyecto` };
    case "catalog_updated":
      return {
        ...base,
        title: `${actor} actualizó el catálogo del taller`,
        detail: dataString(event, "detail") || undefined,
      };
    default:
      return null;
  }
}

function dataNumber(event: ProjectEvent, key: string): number | null {
  const value = event.data[key];
  return typeof value === "number" ? value : null;
}

function liveActivity(
  event: ProjectEvent,
  currentClientId: string | null,
  currentActor: string,
): LiveActivity | null {
  if (isOwnEvent(event, currentActor, currentClientId)) return null;
  const actor = actorLabel(event.actor);
  const action = dataString(event, "action");
  const label = dataString(event, "label");
  const locationPath = dataString(event, "location_path");
  const locationLabel = dataString(event, "location_label");
  return {
    id: event.seq,
    actor,
    clientId: dataString(event, "client_id") || null,
    message: activityMessage(actor, action, label, locationLabel),
    locationPath,
    locationLabel,
  };
}

function activityMessage(
  actor: string,
  action: string,
  label: string,
  locationLabel: string,
): string {
  switch (action) {
    case "editing_costing":
      return `${actor} está editando ${label || "parámetros"}`;
    case "saving_costing":
      return `${actor} está recalculando costos`;
    case "resetting_costing":
      return `${actor} está restableciendo parámetros`;
    case "exporting_budget":
      return `${actor} exportó el presupuesto CSV`;
    default:
      return `${actor} está en ${locationLabel || "el proyecto"}`;
  }
}

function isOwnEvent(
  event: ProjectEvent,
  currentActor: string,
  currentClientId: string | null,
): boolean {
  const eventClientId = dataString(event, "client_id");
  if (eventClientId && currentClientId) return eventClientId === currentClientId;
  return Boolean(event.actor && event.actor === currentActor);
}

function dataString(event: ProjectEvent, key: string): string {
  const value = event.data[key];
  return typeof value === "string" ? value : "";
}

function projectLocationLabel(projectId: string, pathname: string): string {
  const base = `/proyecto/${projectId}`;
  if (pathname === base) return "Resumen";
  if (pathname === `${base}/plano`) return "Visor del Plano";
  if (pathname === `${base}/presupuesto`) return "Presupuesto";
  if (pathname === `${base}/parametros`) return "Parámetros e Insumos";
  if (pathname === `${base}/apus`) return "Precios Unitarios";
  if (pathname === `${base}/programa`) return "Programa de Obra";
  if (pathname === `${base}/flujo`) return "Flujo Financiero";
  if (pathname === `${base}/riesgos`) return "Riesgos";
  return "Proyecto";
}
