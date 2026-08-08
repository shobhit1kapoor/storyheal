import { apiClient } from './api';

export interface AnalyticsSummary {
  questions_processed: number;
  gaps_detected: number;
  contradictions_detected: number;
  stale_content_detected: number;
  drafts_generated: number;
  drafts_approved: number;
  drafts_rejected: number;
  stories_published: number;
  stories_indexed: number;
  storyblok_api_operations: number;
  storyblok_api_failures: number;
  response_accuracy: number;
  resolution_rate: number;
  helpful_rate: number;
  average_response_time_ms: number | null;
  average_indexing_time_ms: number | null;
  improvement_percentage_points: number;
  findings_by_type: Record<string, number>;
  proposals_by_status: Record<string, number>;
  content_types: Record<string, number>;
  locales_indexed: Record<string, number>;
  channels_published: Record<string, number>;
  daily_activity: Array<{ date: string; questions: number; findings: number; drafts: number; published: number }>;
  paired_evaluations: Array<{ proposal_id: string; before: number; after: number; improvement: number }>;
}

export interface StoryblokOperation {
  id: string; proposal_id: string | null; operation: string; method: string;
  status_code: number | null; success: boolean; duration_ms: number | null;
  attempt: number; story_id: string | null; error: string | null; created_at: string;
}

export interface Finding {
  id: string;
  run_id: string;
  kind: string;
  status: string;
  title: string;
  summary: string;
  representative_question: string;
  severity: string;
  confidence: number;
  occurrence_count: number;
  evidence_ids: string[];
  related_story_uuids: string[];
  detected_at: string;
}

export interface Proposal {
  id: string;
  finding_id: string;
  status: string;
  content_type: string;
  title: string;
  slug: string;
  storyblok_story_id: string | null;
  storyblok_uuid: string | null;
  storyblok_full_slug: string | null;
  content_payload: Record<string, unknown>;
  published_snapshot: Record<string, unknown> | null;
  evidence_score: number;
  quality_score: number;
  localization_score: number;
  reviewer_id: string | null;
  review_reason: string | null;
  approved_at: string | null;
  published_at: string | null;
  indexed_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface StoryblokConnection {
  id: string;
  project_id: string;
  region: string;
  space_id: string;
  folder_id: string | null;
  folder_slug: string;
  rag_collection_id: string;
  locales: string[];
  workflow_stage_ids: Record<string, number>;
  component_ids: Record<string, number>;
  public_webhook_url: string;
  is_active: boolean;
  draft_token_configured: boolean;
  publisher_token_configured: boolean;
  delivery_token_configured: boolean;
  webhook_secret_configured: boolean;
  last_tested_at: string | null;
  last_synced_at: string | null;
}

export interface ReviewContext {
  proposal: Proposal;
  finding: Finding | null;
  agent_outputs: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  live_draft: Record<string, unknown> | null;
  published_entry: Record<string, unknown> | null;
  editor_url: string | null;
}

export interface PublicStory {
  story_uuid: string;
  full_slug: string;
  title: string;
  locale: string;
  content_type: string;
  published_at: string | null;
  text: string;
  citations: Array<Record<string, unknown>>;
  channel_variants: Record<string, unknown>;
  metadata: { source_url?: string };
}

export const knowledgeOpsApi = {
  analytics: () => apiClient.get<AnalyticsSummary>('/v1/knowledge-ops/analytics'),
  findings: () => apiClient.get<Finding[]>('/v1/knowledge-ops/findings'),
  proposals: () => apiClient.get<Proposal[]>('/v1/knowledge-ops/proposals'),
  audit: () => apiClient.get<AuditEvent[]>('/v1/knowledge-ops/audit-events'),
  operations: () => apiClient.get<StoryblokOperation[]>('/v1/knowledge-ops/storyblok-operations'),
  reviewContext: (id: string) => apiClient.get<ReviewContext>(`/v1/knowledge-ops/proposals/${id}/review-context`),
  approve: (id: string, reason: string) => apiClient.post<Proposal>(`/v1/knowledge-ops/proposals/${id}/approve`, { reason }),
  reject: (id: string, reason: string) => apiClient.post<Proposal>(`/v1/knowledge-ops/proposals/${id}/reject`, { reason }),
  retry: (id: string) => apiClient.post<Proposal>(`/v1/knowledge-ops/proposals/${id}/retry`),
  getConnection: () => apiClient.get<StoryblokConnection>('/v1/storyblok/connection'),
  saveConnection: (payload: Record<string, unknown>) => apiClient.put<StoryblokConnection>('/v1/storyblok/connection', payload),
  testConnection: () => apiClient.post<Record<string, unknown>>('/v1/storyblok/test'),
  provision: () => apiClient.post<Record<string, unknown>>('/v1/storyblok/provision'),
  sync: () => apiClient.post<{ queued: number }>('/v1/storyblok/sync'),
  publicContent: (locale: string) => apiClient.get<{ locale: string; source: string; stories: PublicStory[] }>(
    `/v1/storyblok/public/content?locale=${encodeURIComponent(locale)}`
  ),
};
