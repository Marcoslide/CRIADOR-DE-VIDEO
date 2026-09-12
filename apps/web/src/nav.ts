import type { LucideIcon } from "lucide-react";
import {
  Boxes,
  Clapperboard,
  Cpu,
  Drama,
  FolderKanban,
  HardDrive,
  LayoutDashboard,
  Mic,
  PersonStanding,
  Plug,
  Radio,
  Settings as SettingsIcon,
  ShieldCheck,
  Tv,
  UserSquare2,
  Video,
} from "lucide-react";

export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
  /** Fase do ROADMAP.md em que esta tela ganha funcionalidade real. */
  phase: number | "1";
  implemented: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard, phase: "1", implemented: true },
  { label: "Avatars", path: "/avatars", icon: UserSquare2, phase: 3, implemented: true },
  { label: "Voice Bank", path: "/voices", icon: Mic, phase: 4, implemented: false },
  { label: "Motion Bank", path: "/motions", icon: PersonStanding, phase: 4, implemented: false },
  { label: "Products", path: "/products", icon: Boxes, phase: 4, implemented: false },
  { label: "Characters", path: "/characters", icon: Drama, phase: 5, implemented: false },
  { label: "Channels", path: "/channels", icon: Tv, phase: 5, implemented: false },
  { label: "Scenes", path: "/scenes", icon: Clapperboard, phase: 5, implemented: false },
  { label: "Create Video", path: "/create-video", icon: Video, phase: 5, implemented: false },
  {
    label: "Video Projects",
    path: "/video-projects",
    icon: FolderKanban,
    phase: 8,
    implemented: false,
  },
  { label: "Render Queue", path: "/render-queue", icon: Radio, phase: 8, implemented: false },
  { label: "GPU Engine", path: "/gpu-engine", icon: Cpu, phase: 6, implemented: false },
  { label: "Quality Gate", path: "/quality-gate", icon: ShieldCheck, phase: 9, implemented: false },
  { label: "Storage", path: "/storage", icon: HardDrive, phase: 2, implemented: false },
  { label: "Integrations", path: "/integrations", icon: Plug, phase: 2, implemented: false },
  { label: "Settings", path: "/settings", icon: SettingsIcon, phase: "1", implemented: false },
];
