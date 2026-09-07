import { useEffect, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import { listSchedules, type ScheduleOut } from "../../lib/api";

const STATUS_COLOR: Record<string, string> = {
  todo: "#64748b",
  in_progress: "#886AFF",
  done: "#22c55e",
};

export default function CalendarView() {
  const [schedules, setSchedules] = useState<ScheduleOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    listSchedules(true)
      .then((data) => {
        setSchedules(data);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const events = schedules
    .filter((s) => s.task && s.calendar_start)
    .map((s) => ({
      id: s.id,
      title: s.task!.title,
      start: s.calendar_start!,
      end: s.calendar_end ?? undefined,
      color: STATUS_COLOR[s.task!.status] ?? STATUS_COLOR.todo,
      extendedProps: { dept: s.task!.dept, progress_pct: s.task!.progress_pct },
    }));

  return (
    <div className="flex h-full flex-col p-6 text-slate-100">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Calendar</h1>
        <button
          onClick={load}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
        >
          새로고침
        </button>
      </div>
      {error && <div className="mb-4 text-sm text-red-400">{error}</div>}
      {loading ? (
        <div className="text-slate-400">불러오는 중...</div>
      ) : (
        <div className="flex-1 overflow-auto rounded-lg bg-white p-4 text-slate-900">
          <FullCalendar
            plugins={[dayGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            events={events}
            height="auto"
          />
        </div>
      )}
    </div>
  );
}
