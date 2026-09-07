import Phaser from "phaser";
import type { AgentStatusOut, DeskOut } from "../../lib/api";

export interface Room {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  cols: number;
  rows: number;
  accent: number;
}

export const ROOMS: Room[] = [
  { name: "대표실", x: 30, y: 30, w: 300, h: 220, cols: 4, rows: 3, accent: 0xf5c451 },
  { name: "개발실", x: 570, y: 30, w: 300, h: 220, cols: 4, rows: 3, accent: 0x38bdf8 },
  { name: "경영지원실", x: 30, y: 390, w: 300, h: 220, cols: 4, rows: 3, accent: 0x34d399 },
  { name: "마케팅실", x: 570, y: 390, w: 300, h: 220, cols: 4, rows: 3, accent: 0xf472b6 },
];

const OFFICE_W = 900;
const OFFICE_H = 640;
const OFFICE_FLOOR_KEY = "floor_wood";

const HEADER_H = 30;
const MEETING_ZONE = { x: 340, y: 260, w: 220, h: 120 };
const CEO_HOME = { x: 180, y: 150 };
const CEO_MEETING_SPOT = { x: 400, y: 335 };
const MEETING_MID_X = MEETING_ZONE.x + MEETING_ZONE.w / 2;
const MEETING_MID_Y = MEETING_ZONE.y + MEETING_ZONE.h / 2 + 6;
// Goal형 병렬 실행으로 여러 Worker가 동시에 활성화될 수 있어 좌석을 여러 개 두고
// 활성화되는 순서대로 빈 좌석에 배정한다(고정 좌표 1개만 쓰면 아바타들이 겹쳐 보임)
const GUEST_SEATS = [
  { x: MEETING_MID_X - 16, y: MEETING_MID_Y - 24 },
  { x: MEETING_MID_X + 16, y: MEETING_MID_Y - 24 },
  { x: MEETING_MID_X - 16, y: MEETING_MID_Y + 24 },
  { x: MEETING_MID_X + 16, y: MEETING_MID_Y + 24 },
];
const WALK_SPEED = 90; // px/s
const ARRIVE_EPS = 3;
// 아바타(책상 뒤에 서있는 위치)와 책상 이미지(cellRect 중심에서 살짝 앞으로)가 겹치지 않도록 서로 반대 방향으로 띄운다
const AVATAR_DESK_OFFSET_Y = 8;
const DESK_FURNITURE_OFFSET_Y = 10;
const CEO_KEY = "__ceo__";

const DEPT_COLOR: Record<string, number> = {
  CTO: 0x38bdf8,
  CMO: 0xf472b6,
  CPO: 0x886aff,
  CSO: 0xfbbf24,
  CFO: 0x34d399,
};
const DEPT_SPRITE: Record<string, string> = {
  CTO: "cto",
  CMO: "cmo",
  CPO: "cpo",
  CSO: "cso",
  CFO: "cfo",
};
const DEFAULT_AVATAR_COLOR = 0x94a3b8;
const DEFAULT_SPRITE = "cpo";
const CEO_COLOR = 0xf5c451;

const ASSET_BASE = "/assets/metaverse";
const FLOOR_KEYS = ["floor_wood", "floor_green"];
const PROP_KEYS = ["table", "chair", "plant", "cabinet"];
const CHAR_ROLES = ["ceo", "cfo", "cmo", "cto", "cso", "cpo"];
// LPC(Liberated Pixel Cup) 표준 걷기 스프라이트시트 레이아웃 - 64x64 프레임, 9프레임 x 4방향
const LPC_FRAME = 64;
const LPC_FRAMES_PER_ROW = 9;
type Facing = "up" | "left" | "down" | "right";
const LPC_ROW: Record<Facing, number> = { up: 0, left: 1, down: 2, right: 3 };

function cellRect(room: Room, gx: number, gy: number) {
  const cellW = room.w / room.cols;
  const cellH = (room.h - HEADER_H) / room.rows;
  return { x: room.x + gx * cellW, y: room.y + HEADER_H + gy * cellH, w: cellW, h: cellH };
}

type AvatarPhase = "at_desk" | "to_meeting" | "at_meeting" | "to_desk";

interface AvatarState {
  key: string;
  label: string;
  color: number;
  spriteKey: string;
  homeX: number;
  homeY: number;
  meetingX: number;
  meetingY: number;
  x: number;
  y: number;
  dx: number;
  dy: number;
  manualTarget: { x: number; y: number } | null;
  facing: Facing;
  phase: AvatarPhase;
  walkCycle: number;
  bobSeed: number;
  lastRun: AgentStatusOut["last_run"] | null;
}

export class OfficeScene extends Phaser.Scene {
  private desks: DeskOut[] = [];
  private onCellClick?: (room: string, gridX: number, gridY: number) => void;
  private onDeskClick?: (desk: DeskOut) => void;

  private staticGraphics!: Phaser.GameObjects.Graphics;
  private avatarGraphics!: Phaser.GameObjects.Graphics;
  private deskLabelTexts: Map<string, Phaser.GameObjects.Text> = new Map();
  private deskFurniture: Map<string, Phaser.GameObjects.Image> = new Map();
  private speechBubbles: Map<string, { bg: Phaser.GameObjects.Graphics; text: Phaser.GameObjects.Text }> =
    new Map();

  private avatars: Map<string, AvatarState> = new Map();
  private avatarImages: Map<string, Phaser.GameObjects.Sprite> = new Map();
  private seatAssignments: Map<string, number> = new Map(); // avatar key -> GUEST_SEATS 인덱스
  private elapsed = 0;

  constructor() {
    super("OfficeScene");
  }

  preload() {
    for (const key of FLOOR_KEYS) this.load.image(key, `${ASSET_BASE}/${key}.png`);
    for (const key of PROP_KEYS) this.load.image(key, `${ASSET_BASE}/${key}.png`);
    for (const role of CHAR_ROLES) {
      this.load.spritesheet(`char_${role}`, `${ASSET_BASE}/lpc/char_${role}_walk.png`, {
        frameWidth: LPC_FRAME,
        frameHeight: LPC_FRAME,
      });
    }
  }

  create() {
    this.staticGraphics = this.add.graphics().setDepth(1);
    this.avatarGraphics = this.add.graphics().setDepth(4);
    this.input.on("pointerdown", this.handlePointerDown, this);
    this.createCharacterAnims();
    this.drawStatic();
    this.ensureCeoAvatar();
  }

  private createCharacterAnims() {
    for (const role of CHAR_ROLES) {
      for (const facing of Object.keys(LPC_ROW) as Facing[]) {
        const row = LPC_ROW[facing];
        const key = `char_${role}_walk_${facing}`;
        if (this.anims.exists(key)) continue;
        this.anims.create({
          key,
          frames: this.anims.generateFrameNumbers(`char_${role}`, {
            start: row * LPC_FRAMES_PER_ROW,
            end: row * LPC_FRAMES_PER_ROW + LPC_FRAMES_PER_ROW - 1,
          }),
          frameRate: 10,
          repeat: -1,
        });
      }
    }
  }

  setCallbacks(
    onCellClick: (room: string, gridX: number, gridY: number) => void,
    onDeskClick: (desk: DeskOut) => void,
  ) {
    this.onCellClick = onCellClick;
    this.onDeskClick = onDeskClick;
  }

  setData(desks: DeskOut[], agentStatus: AgentStatusOut[]) {
    this.setDesks(desks);
    this.setAgentStatus(agentStatus);
  }

  setDesks(desks: DeskOut[]) {
    this.desks = desks;
    this.syncAvatarsFromDesks();
    this.redrawDeskLabels();
  }

  setAgentStatus(agentStatus: AgentStatusOut[]) {
    const byName = new Map(agentStatus.map((a) => [a.agent_name, a]));
    let anyActive = false;

    for (const avatar of this.avatars.values()) {
      if (avatar.key === CEO_KEY) continue;
      const status = byName.get(avatar.label);
      avatar.lastRun = status?.last_run ?? null;
      const active = status?.status === "active";
      if (active) anyActive = true;
      if (active && avatar.phase === "at_desk") {
        const seat = this.allocateSeat(avatar.key);
        avatar.meetingX = seat.x;
        avatar.meetingY = seat.y;
        avatar.phase = "to_meeting";
      }
      if (!active && (avatar.phase === "at_meeting" || avatar.phase === "to_meeting")) {
        avatar.phase = "to_desk";
        this.releaseSeat(avatar.key);
      }
    }

    const ceo = this.avatars.get(CEO_KEY);
    if (ceo) {
      if (anyActive && ceo.phase === "at_desk") ceo.phase = "to_meeting";
      if (!anyActive && (ceo.phase === "at_meeting" || ceo.phase === "to_meeting")) {
        ceo.phase = "to_desk";
      }
    }
  }

  private allocateSeat(key: string): { x: number; y: number } {
    const existing = this.seatAssignments.get(key);
    if (existing !== undefined) return GUEST_SEATS[existing];
    const taken = new Set(this.seatAssignments.values());
    let index = GUEST_SEATS.findIndex((_, i) => !taken.has(i));
    if (index === -1) index = 0; // 좌석이 다 찼으면(4개 이상 동시 활성) 겹치더라도 첫 좌석에 배정
    this.seatAssignments.set(key, index);
    return GUEST_SEATS[index];
  }

  private releaseSeat(key: string) {
    this.seatAssignments.delete(key);
  }

  update(_time: number, delta: number) {
    const dt = delta / 1000;
    this.elapsed += dt;
    for (const avatar of this.avatars.values()) {
      this.stepAvatar(avatar, dt);
    }
    this.drawAvatars();
    this.updateSpeechBubbles();
  }

  private ensureCeoAvatar() {
    if (this.avatars.has(CEO_KEY)) return;
    this.avatars.set(CEO_KEY, {
      key: CEO_KEY,
      label: "CEO",
      color: CEO_COLOR,
      spriteKey: "ceo",
      homeX: CEO_HOME.x,
      homeY: CEO_HOME.y,
      meetingX: CEO_MEETING_SPOT.x,
      meetingY: CEO_MEETING_SPOT.y,
      x: CEO_HOME.x,
      y: CEO_HOME.y,
      dx: 0,
      dy: 0,
      manualTarget: null,
      facing: "down",
      phase: "at_desk",
      walkCycle: 0,
      bobSeed: Math.random() * 1000,
      lastRun: null,
    });
    this.avatarImages.set(
      CEO_KEY,
      this.add.sprite(CEO_HOME.x, CEO_HOME.y, "char_ceo", LPC_ROW.down * LPC_FRAMES_PER_ROW).setScale(0.55).setDepth(5),
    );
  }

  private syncAvatarsFromDesks() {
    const activeKeys = new Set(this.desks.map((d) => d.id));
    for (const key of Array.from(this.avatars.keys())) {
      if (key === CEO_KEY || activeKeys.has(key)) continue;
      this.avatars.delete(key);
      const bubble = this.speechBubbles.get(key);
      bubble?.bg.destroy();
      bubble?.text.destroy();
      this.speechBubbles.delete(key);
      this.deskLabelTexts.get(key)?.destroy();
      this.deskLabelTexts.delete(key);
      this.avatarImages.get(key)?.destroy();
      this.avatarImages.delete(key);
      this.releaseSeat(key);
    }

    for (const desk of this.desks) {
      const room = ROOMS.find((r) => r.name === desk.room);
      if (!room) continue;
      const rect = cellRect(room, desk.grid_x, desk.grid_y);
      const homeX = rect.x + rect.w / 2;
      const homeY = rect.y + rect.h / 2 - AVATAR_DESK_OFFSET_Y;
      const color = DEPT_COLOR[desk.dept ?? ""] ?? DEFAULT_AVATAR_COLOR;
      const spriteKey = DEPT_SPRITE[desk.dept ?? ""] ?? DEFAULT_SPRITE;
      const existing = this.avatars.get(desk.id);
      if (existing) {
        existing.homeX = homeX;
        existing.homeY = homeY;
        existing.label = desk.label ?? desk.dept ?? "";
        existing.color = color;
        existing.spriteKey = spriteKey;
      } else {
        this.avatars.set(desk.id, {
          key: desk.id,
          label: desk.label ?? desk.dept ?? "",
          color,
          spriteKey,
          homeX,
          homeY,
          meetingX: GUEST_SEATS[0].x,
          meetingY: GUEST_SEATS[0].y,
          x: homeX,
          y: homeY,
          dx: 0,
          dy: 0,
          manualTarget: null,
          facing: "down",
          phase: "at_desk",
          walkCycle: 0,
          bobSeed: Math.random() * 1000,
          lastRun: null,
        });
        this.avatarImages.set(
          desk.id,
          this.add
            .sprite(homeX, homeY, `char_${spriteKey}`, LPC_ROW.down * LPC_FRAMES_PER_ROW)
            .setScale(0.55)
            .setDepth(5),
        );
      }
    }
  }

  private stepAvatar(avatar: AvatarState, dt: number) {
    const manual = avatar.key === CEO_KEY ? avatar.manualTarget : null;
    const target = manual
      ? manual
      : avatar.phase === "to_meeting"
        ? { x: avatar.meetingX, y: avatar.meetingY }
        : avatar.phase === "to_desk"
          ? { x: avatar.homeX, y: avatar.homeY }
          : null;
    if (!target) {
      avatar.dx = 0;
      avatar.dy = 0;
      return;
    }

    const dx = target.x - avatar.x;
    const dy = target.y - avatar.y;
    const dist = Math.hypot(dx, dy);
    if (dist < ARRIVE_EPS) {
      avatar.x = target.x;
      avatar.y = target.y;
      if (manual) {
        avatar.manualTarget = null;
      } else {
        avatar.phase = avatar.phase === "to_meeting" ? "at_meeting" : "at_desk";
      }
      avatar.dx = 0;
      avatar.dy = 0;
    } else {
      const step = Math.min(WALK_SPEED * dt, dist);
      avatar.x += (dx / dist) * step;
      avatar.y += (dy / dist) * step;
      avatar.walkCycle += dt * 8;
      avatar.dx = dx;
      avatar.dy = dy;
      avatar.facing = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up";
    }
  }

  private drawStatic() {
    const g = this.staticGraphics;
    g.clear();

    // 오피스 전체를 하나의 바닥재로 통일 — 복도까지 이어져서 CEO가 자유롭게 걸어다녀도 어색하지 않다
    this.add
      .tileSprite(0, 0, OFFICE_W, OFFICE_H, OFFICE_FLOOR_KEY)
      .setOrigin(0, 0)
      .setTileScale(2, 2)
      .setDepth(0);

    for (const room of ROOMS) {
      g.lineStyle(3, room.accent, 0.55);
      g.strokeRoundedRect(room.x, room.y, room.w, room.h, 8);

      this.add.rectangle(room.x + room.w / 2, room.y + HEADER_H / 2, room.w, HEADER_H, 0x0f172a, 0.55).setDepth(2);
      this.add
        .text(room.x + 10, room.y + 6, room.name, {
          fontSize: "14px",
          color: "#e2e8f0",
          fontStyle: "bold",
        })
        .setDepth(3);

      g.lineStyle(1, 0xffffff, 0.08);
      for (let gx = 1; gx < room.cols; gx++) {
        const lx = room.x + (room.w / room.cols) * gx;
        g.lineBetween(lx, room.y + HEADER_H, lx, room.y + room.h);
      }
      for (let gy = 1; gy < room.rows; gy++) {
        const ly = room.y + HEADER_H + ((room.h - HEADER_H) / room.rows) * gy;
        g.lineBetween(room.x, ly, room.x + room.w, ly);
      }

      this.add.image(room.x + room.w - 20, room.y + room.h - 20, "plant").setScale(1.6).setDepth(1);
      this.add.image(room.x + 22, room.y + HEADER_H + 18, "cabinet").setScale(1.6).setDepth(1);
    }

    // 회의실 존
    const mz = MEETING_ZONE;
    this.add
      .tileSprite(mz.x, mz.y, mz.w, mz.h, "floor_green")
      .setOrigin(0, 0)
      .setTileScale(2, 2)
      .setDepth(0);
    g.lineStyle(2, 0x886aff, 0.5);
    g.strokeRoundedRect(mz.x, mz.y, mz.w, mz.h, 10);

    this.add.image(MEETING_MID_X - 16, MEETING_MID_Y, "table").setScale(2).setDepth(1);
    this.add.image(MEETING_MID_X + 16, MEETING_MID_Y, "table").setScale(2).setDepth(1);
    for (const seat of GUEST_SEATS) {
      const flip = seat.y > MEETING_MID_Y;
      this.add.image(seat.x, seat.y, "chair").setScale(1.5).setFlipY(flip).setDepth(1);
    }

    this.add
      .text(mz.x + mz.w / 2, mz.y + 8, "회의실", {
        fontSize: "12px",
        color: "#a78bfa",
        fontStyle: "bold",
      })
      .setOrigin(0.5, 0)
      .setDepth(3);
  }

  private redrawDeskLabels() {
    const seen = new Set<string>();
    for (const desk of this.desks) {
      const room = ROOMS.find((r) => r.name === desk.room);
      if (!room) continue;
      const rect = cellRect(room, desk.grid_x, desk.grid_y);
      const cx = rect.x + rect.w / 2;
      const cy = rect.y + rect.h / 2 + DESK_FURNITURE_OFFSET_Y;
      const labelY = rect.y + rect.h - 12;
      const label = desk.label ?? desk.dept ?? "";
      seen.add(desk.id);

      let furniture = this.deskFurniture.get(desk.id);
      if (!furniture) {
        furniture = this.add.image(cx, cy, "table").setScale(1.7).setDepth(1);
        this.deskFurniture.set(desk.id, furniture);
      } else {
        furniture.setPosition(cx, cy);
      }

      let text = this.deskLabelTexts.get(desk.id);
      if (!text) {
        text = this.add
          .text(cx, labelY, label, { fontSize: "9px", color: "#cbd5e1" })
          .setOrigin(0.5, 0)
          .setDepth(3);
        this.deskLabelTexts.set(desk.id, text);
      } else {
        text.setText(label);
        text.setPosition(cx, labelY);
      }
    }
    for (const [key, text] of this.deskLabelTexts.entries()) {
      if (!seen.has(key)) {
        text.destroy();
        this.deskLabelTexts.delete(key);
        this.deskFurniture.get(key)?.destroy();
        this.deskFurniture.delete(key);
      }
    }
  }

  private drawAvatars() {
    this.avatarGraphics.clear();
    for (const avatar of this.avatars.values()) {
      this.drawOneAvatar(avatar);
    }
  }

  private drawOneAvatar(avatar: AvatarState) {
    const g = this.avatarGraphics;
    const walking =
      avatar.phase === "to_meeting" || avatar.phase === "to_desk" || !!avatar.manualTarget;
    const bob = walking
      ? Math.sin(avatar.walkCycle * 2) * 1.5
      : Math.sin(this.elapsed * 2.4 + avatar.bobSeed) * 1.5;
    const baseY = avatar.y + bob;

    g.fillStyle(0x000000, 0.28);
    g.fillEllipse(avatar.x, avatar.y + 16, 16, 5);

    const sprite = this.avatarImages.get(avatar.key);
    if (sprite) {
      sprite.setPosition(avatar.x, baseY);
      const animKey = `char_${avatar.spriteKey}_walk_${avatar.facing}`;
      if (walking) {
        if (sprite.anims.currentAnim?.key !== animKey || !sprite.anims.isPlaying) {
          sprite.play(animKey);
        }
      } else {
        sprite.anims.stop();
        sprite.setFrame(LPC_ROW[avatar.facing] * LPC_FRAMES_PER_ROW);
      }
    }

    if (avatar.phase === "at_meeting" || avatar.phase === "to_meeting") {
      g.lineStyle(2, 0x22c55e, 0.7);
      g.strokeCircle(avatar.x, baseY, 20);
    }
  }

  private updateSpeechBubbles() {
    for (const avatar of this.avatars.values()) {
      if (avatar.key === CEO_KEY) continue;
      const show = avatar.phase === "at_meeting" && !!avatar.lastRun?.input?.ceo_directive;

      let bubble = this.speechBubbles.get(avatar.key);
      if (!bubble) {
        const bg = this.add.graphics().setDepth(6);
        const text = this.add
          .text(0, 0, "", {
            fontSize: "10px",
            color: "#0f172a",
            wordWrap: { width: 150 },
          })
          .setDepth(7);
        bubble = { bg, text };
        this.speechBubbles.set(avatar.key, bubble);
      }

      bubble.bg.setVisible(show);
      bubble.text.setVisible(show);
      if (!show) continue;

      const directive = String(avatar.lastRun?.input?.ceo_directive ?? "");
      const summary = directive.length > 40 ? `${directive.slice(0, 40)}…` : directive;
      bubble.text.setText(summary);

      const bx = avatar.x - 75;
      const by = avatar.y - 58;
      bubble.text.setPosition(bx + 8, by + 6);

      bubble.bg.clear();
      bubble.bg.fillStyle(0xf8fafc, 0.95);
      bubble.bg.fillRoundedRect(bx, by, 150, bubble.text.height + 12, 6);
    }
  }

  private handlePointerDown(pointer: Phaser.Input.Pointer) {
    const { x, y } = pointer;
    for (const room of ROOMS) {
      if (x < room.x || x > room.x + room.w || y < room.y + HEADER_H || y > room.y + room.h) continue;

      const cellW = room.w / room.cols;
      const cellH = (room.h - HEADER_H) / room.rows;
      const gx = Math.floor((x - room.x) / cellW);
      const gy = Math.floor((y - room.y - HEADER_H) / cellH);

      const existing = this.desks.find(
        (d) => d.room === room.name && d.grid_x === gx && d.grid_y === gy,
      );
      if (existing) {
        this.onDeskClick?.(existing);
      } else {
        this.onCellClick?.(room.name, gx, gy);
      }
      return;
    }

    // 룸의 책상 그리드 밖(복도/회의실 공터 등 자유 공간) 클릭 → CEO를 그 위치로 이동시킨다
    const ceo = this.avatars.get(CEO_KEY);
    if (ceo) {
      ceo.manualTarget = {
        x: Phaser.Math.Clamp(x, 12, OFFICE_W - 12),
        y: Phaser.Math.Clamp(y, 12, OFFICE_H - 12),
      };
    }
  }
}
