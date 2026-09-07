import { useEffect, useRef, useState } from "react";
import Phaser from "phaser";
import { OfficeScene } from "./OfficeScene";
import {
  getAgentStatusWsUrl,
  createDesk,
  deleteDesk,
  getAgentStatus,
  listDesks,
  type AgentStatusOut,
  type DeskOut,
} from "../../lib/api";

const AGENT_TO_DEPT: Record<string, string> = {
  Supervisor: "",
  BizDevWorker: "CSO",
  PMWorker: "CPO",
  MarketingWorker: "CMO",
  DevWorker: "CTO",
};
const AGENT_OPTIONS = Object.keys(AGENT_TO_DEPT);

export default function MetaverseView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);
  const sceneRef = useRef<OfficeScene | null>(null);

  const [desks, setDesks] = useState<DeskOut[]>([]);
  const [agentStatus, setAgentStatus] = useState<AgentStatusOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedDesk, setSelectedDesk] = useState<DeskOut | null>(null);
  const [pendingCell, setPendingCell] = useState<{
    room: string;
    grid_x: number;
    grid_y: number;
  } | null>(null);

  const loadDesks = () => {
    listDesks()
      .then(setDesks)
      .catch((e) => setError((e as Error).message));
  };

  const loadAgentStatus = () => {
    getAgentStatus()
      .then(setAgentStatus)
      .catch(() => {});
  };

  useEffect(() => {
    if (!containerRef.current) return;

    const game = new Phaser.Game({
      type: Phaser.AUTO,
      width: 900,
      height: 640,
      parent: containerRef.current,
      backgroundColor: "#0f172a",
      scene: [OfficeScene],
    });
    gameRef.current = game;

    game.events.once(Phaser.Core.Events.READY, () => {
      const scene = game.scene.getScene("OfficeScene") as OfficeScene;
      sceneRef.current = scene;
      scene.setCallbacks(
        (room, gx, gy) => setPendingCell({ room, grid_x: gx, grid_y: gy }),
        (desk) => setSelectedDesk(desk),
      );
      scene.setData(desks, agentStatus);
    });

    loadDesks();
    loadAgentStatus(); // WebSocket 연결 전 첫 화면을 바로 채우기 위한 1회성 REST 호출

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let closedByUs = false;

    const connect = () => {
      socket = new WebSocket(getAgentStatusWsUrl());
      socket.onmessage = (event) => {
        try {
          setAgentStatus(JSON.parse(event.data));
        } catch {
          // ignore malformed frame
        }
      };
      socket.onclose = () => {
        if (closedByUs) return;
        reconnectTimer = setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      closedByUs = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      game.destroy(true);
      gameRef.current = null;
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    sceneRef.current?.setDesks(desks);
  }, [desks]);

  useEffect(() => {
    sceneRef.current?.setAgentStatus(agentStatus);
  }, [agentStatus]);

  const handleAddDesk = async (agentName: string) => {
    if (!pendingCell) return;
    try {
      await createDesk({ ...pendingCell, label: agentName, dept: AGENT_TO_DEPT[agentName] });
      setPendingCell(null);
      loadDesks();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleDeleteDesk = async () => {
    if (!selectedDesk) return;
    try {
      await deleteDesk(selectedDesk.id);
      setSelectedDesk(null);
      loadDesks();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const selectedStatus = selectedDesk
    ? agentStatus.find((a) => a.agent_name === selectedDesk.label)
    : undefined;

  return (
    <div className="relative flex h-full flex-col gap-3 p-6 text-slate-100">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Metaverse Office</h1>
        <span className="text-xs text-slate-500">
          룸 안 빈 칸을 클릭해 책상을 추가하고, 책상을 클릭해 상태를 확인하세요 — 그 외 빈 공간을 클릭하면 CEO가 그곳으로 이동합니다
        </span>
      </div>
      {error && <div className="text-sm text-red-400">{error}</div>}
      <div
        ref={containerRef}
        className="overflow-hidden rounded-lg border border-slate-800"
        style={{ width: 900, height: 640 }}
      />

      {pendingCell && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-black/50"
          onClick={() => setPendingCell(null)}
        >
          <div
            className="rounded-lg border border-slate-700 bg-slate-900 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-3 text-sm font-medium">{pendingCell.room}에 책상 추가</h2>
            <div className="flex flex-col gap-2">
              {AGENT_OPTIONS.map((agent) => (
                <button
                  key={agent}
                  onClick={() => handleAddDesk(agent)}
                  className="rounded-md border border-slate-700 px-3 py-1.5 text-left text-sm hover:bg-slate-800"
                >
                  {agent}
                </button>
              ))}
            </div>
            <button
              onClick={() => setPendingCell(null)}
              className="mt-3 text-xs text-slate-500 hover:text-slate-300"
            >
              취소
            </button>
          </div>
        </div>
      )}

      {selectedDesk && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-black/50"
          onClick={() => setSelectedDesk(null)}
        >
          <div
            className="max-w-md rounded-lg border border-slate-700 bg-slate-900 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-sm font-medium">
              {selectedDesk.label ?? selectedDesk.dept ?? "(이름 없음)"}
            </h2>
            {selectedStatus?.last_run ? (
              <div className="text-xs text-slate-400">
                <p>상태: {selectedStatus.status === "active" ? "🟢 작업중" : "⚪ 대기"}</p>
                <p className="mt-1">
                  최근 실행: {new Date(selectedStatus.last_run.started_at).toLocaleString()}
                </p>
                {selectedStatus.last_run.finished_at && (
                  <p className="mt-1 text-slate-500">
                    완료: {new Date(selectedStatus.last_run.finished_at).toLocaleString()}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500">최근 작업 기록이 없습니다.</p>
            )}
            <button
              onClick={handleDeleteDesk}
              className="mt-3 rounded-md border border-red-800 px-3 py-1.5 text-xs text-red-400 hover:bg-red-950"
            >
              책상 제거
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
