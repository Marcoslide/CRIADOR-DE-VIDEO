// Espelha packages/schemas/dhf_schemas/health.py — mantenha em sincronia manualmente
// até termos geração automática de client a partir do OpenAPI (fase futura).

export type ComponentStatus = "connected" | "error" | "timeout" | "not_configured";

export interface ComponentCheck {
  name: string;
  status: ComponentStatus;
  latency_ms: number | null;
  detail: string | null;
  error_code: string | null;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  app_env: string;
}

export interface ReadinessResponse {
  ready: boolean;
  checks: ComponentCheck[];
  checked_at: string;
}

// Espelha packages/schemas/dhf_schemas/storage.py
export type StorageConnectionStatus = "not_configured" | "connecting" | "connected" | "degraded" | "error";

export interface TreeValidationResult {
  expected: string[];
  found: string[];
  missing: string[];
  unexpected: string[];
  valid: boolean;
}

export interface StorageStatus {
  status: StorageConnectionStatus;
  detail: string | null;
  error_code: string | null;
  root_folder_id: string | null;
  tree: TreeValidationResult | null;
  checked_at: string;
}

// Espelha packages/schemas/dhf_schemas/system_status.py
export type EngineStatusValue = "connected" | "not_configured" | "not_installed" | "error";

export interface GpuStatus {
  status: EngineStatusValue;
  detail: string | null;
  device_name: string | null;
  driver_version: string | null;
  vram_total_mb: number | null;
  vram_used_mb: number | null;
}

export interface OpenAIStatus {
  status: EngineStatusValue;
  detail: string | null;
  error_code: string | null;
}

export interface EngineStubStatus {
  name: string;
  status: EngineStatusValue;
  detail: string | null;
}

export interface SystemStatusResponse {
  checked_at: string;
  api: ComponentCheck;
  postgres: ComponentCheck;
  redis: ComponentCheck;
  worker: ComponentCheck;
  storage: StorageStatus;
  gpu: GpuStatus;
  openai: OpenAIStatus;
  unreal: EngineStubStatus;
  audio2face: EngineStubStatus;
  metahuman: EngineStubStatus;
}

// Espelha packages/schemas/dhf_schemas/jobs.py
export type JobState = "pending" | "started" | "success" | "failure" | "unknown";

export interface DiagnosticJobSubmitted {
  job_id: string;
  triggered_at: string;
}

export interface DiagnosticJobStatus {
  job_id: string;
  state: JobState;
  result: Record<string, unknown> | null;
}

// Espelha core/avatars/dhf_avatars/schemas.py
export type AvatarStatus =
  | "draft"
  | "identity_locked"
  | "multiview_in_progress"
  | "multiview_approved"
  | "mesh_in_progress"
  | "mesh_approved"
  | "rigged"
  | "materials_approved"
  | "face_approved"
  | "voice_approved"
  | "motion_approved"
  | "master_approved"
  | "production_ready";

export interface Avatar {
  id: string;
  name: string;
  slug: string;
  version: number;
  status: AvatarStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AvatarCreatePayload {
  name: string;
  slug: string;
  metadata?: Record<string, unknown>;
}

// Espelha core/avatar_factory/dhf_avatar_factory/schemas.py (Avatar Factory Control Plane)

export type IdentityLockStatus = "draft" | "approved" | "superseded";

export interface FaceIdentitySpec {
  face_shape?: string | null;
  symmetry_notes?: string | null;
  nose_shape?: string | null;
  jaw_shape?: string | null;
  cheekbones?: string | null;
}

export interface EyeIdentitySpec {
  eye_shape?: string | null;
  eye_distance?: string | null;
  eye_color?: string | null;
  iris_pattern?: string | null;
}

export interface MouthIdentitySpec {
  lip_shape?: string | null;
  lip_thickness?: string | null;
  mouth_width?: string | null;
  teeth_alignment?: string | null;
  teeth_color?: string | null;
  has_dental_appliance?: boolean | null;
}

export interface HairIdentitySpec {
  hairline?: string | null;
  hair_color?: string | null;
  hair_texture?: string | null;
  hair_length?: string | null;
  hair_part?: string | null;
}

export interface BodyIdentitySpec {
  build?: string | null;
  skin_tone?: string | null;
  skin_marks?: string | null;
  ear_shape?: string | null;
  ear_visibility?: string | null;
}

export interface HandIdentitySpec {
  hand_shape?: string | null;
  nail_notes?: string | null;
}

export interface ClothingIdentitySpec {
  base_clothing_description?: string | null;
}

export interface IdentitySpec {
  face: FaceIdentitySpec;
  eyes: EyeIdentitySpec;
  mouth: MouthIdentitySpec;
  hair: HairIdentitySpec;
  body: BodyIdentitySpec;
  hands: HandIdentitySpec;
  clothing: ClothingIdentitySpec;
}

export interface IdentityLock {
  id: string;
  avatar_id: string;
  identity_version: number;
  status: IdentityLockStatus;
  identity_spec: IdentitySpec;
  height_cm: number | null;
  notes: string | null;
  source_asset_ids: string[];
  checksum: string | null;
  approved_by: string | null;
  approved_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface IdentityLockUpsertPayload {
  identity_spec: IdentitySpec;
  height_cm?: number | null;
  notes?: string | null;
  source_asset_ids?: string[];
}

export const HEAD_360 = "head_360";
export const HALF_BODY_360 = "half_body_360";
export const FULL_BODY_360 = "full_body_360";
export const ANGLE_360_CATEGORIES = [HEAD_360, HALF_BODY_360, FULL_BODY_360] as const;

export const SPECIALIZED_CATEGORIES = [
  "face_front_neutral",
  "face_left_profile",
  "face_right_profile",
  "face_3q_left",
  "face_3q_right",
  "eyes_close",
  "left_eye_close",
  "right_eye_close",
  "iris_reference",
  "skin_close",
  "pores_reference",
  "mouth_closed",
  "mouth_open",
  "teeth_front",
  "teeth_side",
  "gums",
  "tongue",
  "ear_left",
  "ear_right",
  "hairline_front",
  "hairline_left",
  "hairline_right",
  "hair_back",
  "hand_left_front",
  "hand_left_back",
  "hand_right_front",
  "hand_right_back",
  "nails",
  "feet",
  "body_front",
  "body_back",
  "body_left",
  "body_right",
] as const;

export const EXPRESSION_CATEGORIES = [
  "expr_neutral",
  "expr_small_smile",
  "expr_full_smile",
  "expr_serious",
  "expr_concerned",
  "expr_surprised",
  "expr_angry_light",
  "expr_sad_light",
  "expr_eyes_closed",
  "expr_blink_mid",
  "expr_mouth_a",
  "expr_mouth_e",
  "expr_mouth_i",
  "expr_mouth_o",
  "expr_mouth_u",
  "expr_jaw_open",
  "expr_cheek_raise",
  "expr_brow_up",
  "expr_brow_down",
] as const;

export type ReferenceAssetCategory =
  | (typeof ANGLE_360_CATEGORIES)[number]
  | (typeof SPECIALIZED_CATEGORIES)[number]
  | (typeof EXPRESSION_CATEGORIES)[number];

export const REQUIRED_ANGLES = Array.from({ length: 36 }, (_, i) => i * 10);

export type QAStatus = "pass" | "warn" | "fail" | "not_checked" | "requires_human" | "requires_model";

export type RejectionReason =
  | "identity_drift"
  | "angle_wrong"
  | "blur"
  | "lighting"
  | "hair_inconsistent"
  | "body_inconsistent"
  | "hand_inconsistent"
  | "teeth_inconsistent"
  | "background_interference"
  | "clothing_inconsistent"
  | "other";

export const REJECTION_REASONS: RejectionReason[] = [
  "identity_drift",
  "angle_wrong",
  "blur",
  "lighting",
  "hair_inconsistent",
  "body_inconsistent",
  "hand_inconsistent",
  "teeth_inconsistent",
  "background_interference",
  "clothing_inconsistent",
  "other",
];

export interface ReferenceAsset {
  id: string;
  avatar_id: string;
  capture_version: number;
  category: ReferenceAssetCategory;
  angle: number | null;
  capture_type: string | null;
  side: string | null;
  orientation: string | null;
  source: string | null;
  storage_remote_path: string;
  storage_provider_id: string | null;
  checksum: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  resolution_width: number | null;
  resolution_height: number | null;
  upload_state: "uploaded" | "qa_pending" | "approved" | "rejected";
  qa_status: QAStatus;
  qa_detail: Record<string, { status: QAStatus; detail: string }> | null;
  approved: boolean;
  rejection_reason: RejectionReason | null;
  rejection_notes: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface AngleSlot {
  angle: number;
  state: "missing" | "uploaded" | "qa_pending" | "approved" | "rejected";
  asset_id: string | null;
}

export interface MultiviewFamilyProgress {
  total: number;
  done: number;
  slots: AngleSlot[];
}

export interface CategoryProgress {
  category: ReferenceAssetCategory;
  state: "missing" | "uploaded" | "qa_pending" | "approved" | "rejected";
  asset_id: string | null;
}

export interface MultiviewCompleteness {
  head_360: MultiviewFamilyProgress;
  half_body_360: MultiviewFamilyProgress;
  full_body_360: MultiviewFamilyProgress;
  specialized: CategoryProgress[];
  expression: CategoryProgress[];
  specialized_done: number;
  specialized_total: number;
  expression_done: number;
  expression_total: number;
  all_required_approved: boolean;
  open_rejections: number;
}

export type QualityGateName =
  | "identity"
  | "multiview"
  | "mesh"
  | "rig"
  | "materials"
  | "face"
  | "voice"
  | "motion"
  | "master"
  | "production";

export const QUALITY_GATES: QualityGateName[] = [
  "identity",
  "multiview",
  "mesh",
  "rig",
  "materials",
  "face",
  "voice",
  "motion",
  "master",
  "production",
];

export type QualityGateStatus = "not_tested" | "pass" | "warn" | "fail" | "requires_human" | "requires_model";

export interface QualityGate {
  id: string;
  avatar_id: string;
  gate_name: QualityGateName;
  avatar_version_group: number;
  status: QualityGateStatus;
  checklist: Record<string, string>;
  reason: string | null;
  evidence: Record<string, unknown> | null;
  approved_by: string | null;
  approved_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface GateActionPayload {
  expected_version: number;
  actor: string;
  reason?: string | null;
  evidence?: Record<string, unknown> | null;
}

export interface AvatarStateTransition {
  id: string;
  avatar_id: string;
  from_status: AvatarStatus;
  to_status: AvatarStatus;
  actor: string | null;
  reason: string | null;
  evidence: Record<string, unknown> | null;
  quality_gate: QualityGateName | null;
  avatar_version: number;
  created_at: string;
}

export interface DerivedAsset {
  id: string;
  avatar_id: string;
  asset_type: string;
  avatar_version_group: number;
  status: "not_generated" | "queued" | "generating" | "generated" | "failed";
  storage_remote_path: string | null;
  metadata: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface JobContract {
  id: string;
  avatar_id: string;
  job_type: string;
  input_version: number;
  required_assets: string[];
  output_contract: Record<string, unknown>;
  hardware_requirement: "cpu" | "gpu_any" | "rtx_class" | "rtx_4090" | "ai_heavy";
  status: "pending" | "ready" | "blocked" | "running" | "completed" | "failed" | "cancelled";
  attempt: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ReadinessRequirement {
  key: string;
  label: string;
  satisfied: boolean;
}

export interface AvatarReadiness {
  avatar_id: string;
  status: AvatarStatus;
  production_ready: boolean;
  requirements: ReadinessRequirement[];
  missing: string[];
}

export interface AvatarFactoryView {
  avatar_id: string;
  name: string;
  slug: string;
  status: AvatarStatus;
  version: number;
  identity_lock: IdentityLock | null;
  multiview: MultiviewCompleteness;
  quality_gates: QualityGate[];
  derived_assets: DerivedAsset[];
  job_contracts: JobContract[];
  readiness: AvatarReadiness;
}

export interface ApiErrorDetail {
  message: string;
  missing?: string[];
}
