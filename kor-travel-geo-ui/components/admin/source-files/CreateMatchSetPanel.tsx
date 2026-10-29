"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/ui/Panel";
import { getErrorMessage, postJson, requestJson } from "@/lib/api";
import { sourceFilesPaths, type SourceFileCategoryInfo, type SourceFileCategoryCatalog, type SourceMatchSetDetail, type UploadSessionStatus } from "@/lib/source-files";
import type { components } from "@/types/api.gen";

type CreateRequest = components["schemas"]["SourceMatchSetCreateRequest"];

function isRequiredCategory(role: string, profile: CreateRequest["profile"]) {
  return role === "build_required" || (profile === "serving_recommended" && role === "build_recommended");
}

function useMatchSetSources(profile: CreateRequest["profile"], selected: Record<string, string>) {
  const catalog = useQuery({ queryKey: ["source-file-categories"], queryFn: () => requestJson<SourceFileCategoryCatalog>(sourceFilesPaths.categories()) });
  const sessions = useQuery({ queryKey: ["upload-sessions", "all"], queryFn: () => requestJson<UploadSessionStatus[]>(sourceFilesPaths.uploadSessionsList()) });
  const categories = catalog.data?.categories ?? [];
  const registered = (sessions.data ?? []).filter((session) => session.registration_state === "registered");
  const chosen = categories.flatMap((category) => {
    const session = registered.find((item) => item.category === category.category && item.source_file_group_id === selected[category.category]);
    return session ? [{ category, session }] : [];
  });
  const months = [...new Set(chosen.map(({ session }) => session.user_yyyymm))];
  const missing = categories.some((category) => isRequiredCategory(category.role, profile) && !chosen.some((item) => item.category.category === category.category));
  return { catalog, sessions, categories, registered, chosen, months, missing };
}

export function CreateMatchSetPanel({ onCreated }: { onCreated: (detail: SourceMatchSetDetail) => void }) {
  const id = useId();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [profile, setProfile] = useState<CreateRequest["profile"]>("serving_recommended");
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [mixedAcknowledged, setMixedAcknowledged] = useState(false);
  const { catalog, sessions, categories, registered, chosen, months, missing } = useMatchSetSources(profile, selected);
  const create = useMutation({
    mutationFn: () => postJson<SourceMatchSetDetail>(sourceFilesPaths.matchSets(), {
      name: name.trim(), profile,
      items: chosen.map(({ category, session }) => ({ category: category.category, role: category.role, source_file_group_id: session.source_file_group_id, required: isRequiredCategory(category.role, profile), effective_yyyymm: session.user_yyyymm, omitted: false, validation_enabled: true })),
      metadata: { mixed_yyyymm_acknowledged: months.length > 1 && mixedAcknowledged }
    } satisfies CreateRequest),
    onSuccess: (detail) => {
      void queryClient.invalidateQueries({ queryKey: ["source-match-sets"] });
      onCreated(detail);
      setOpen(false);
    }
  });
  const error = catalog.error ?? sessions.error ?? create.error;

  return (
    <Panel title="매칭 세트 생성" actions={<Button aria-expanded={open} onClick={() => setOpen(!open)} type="button">새 매칭 세트 만들기</Button>}>
      {open ? (
        <form onSubmit={(event) => { event.preventDefault(); create.mutate(); }} className="source-stack">
          <p>등록한 원천 그룹을 카테고리마다 선택합니다. 생성한 초안은 검증한 뒤 DB 재구축에 사용합니다.</p>
          <Field><FieldLabel htmlFor={`${id}-name`}>매칭 세트 이름</FieldLabel><Input id={`${id}-name`} value={name} onChange={(event) => setName(event.target.value)} disabled={create.isPending} /></Field>
          <Field><FieldLabel htmlFor={`${id}-profile`}>구성 프로파일</FieldLabel><select aria-label="구성 프로파일" id={`${id}-profile`} value={profile} disabled={create.isPending} onChange={(event) => setProfile(event.target.value as CreateRequest["profile"])}>
            <option value="serving_recommended">권장 구성 (기본·출입구·구역)</option><option value="serving_minimal">기본 구성 (필수 원천)</option>
          </select></Field>
          <div className="max-h-96 overflow-y-auto space-y-3">
            {categories.map((category) => <GroupSelect key={category.category} category={category}
              required={isRequiredCategory(category.role, profile)} sessions={registered} value={selected[category.category]}
              disabled={create.isPending} onChange={(value) => { setSelected({ ...selected, [category.category]: value }); setMixedAcknowledged(false); }} />)}
          </div>
          {months.length > 1 ? <label><input type="checkbox" checked={mixedAcknowledged} disabled={create.isPending} onChange={(event) => setMixedAcknowledged(event.target.checked)} />자료별 기준월이 다른 구성을 확인했습니다 ({months.join(", ")})</label> : null}
          {error ? <p role="alert">{getErrorMessage(error)}</p> : null}
          <Button type="submit" disabled={!name.trim() || !chosen.length || missing || !catalog.data || !!catalog.error || !!sessions.error || (months.length > 1 && !mixedAcknowledged) || create.isPending}>초안 생성</Button>
        </form>
      ) : <p>원천 그룹을 선택해 새 매칭 세트를 만들 수 있습니다.</p>}
    </Panel>
  );
}

function GroupSelect({ category, required, sessions, value, disabled, onChange }: {
  category: SourceFileCategoryInfo;
  required: boolean;
  sessions: UploadSessionStatus[];
  value?: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const id = useId();
  const label = `${category.label} (${required ? "필수" : "선택"})`;
  return (
    <Field><FieldLabel htmlFor={id}>{label}</FieldLabel>
      <select aria-label={label} id={id} value={value ?? ""} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        <option value="">그룹 선택</option>
        {sessions.filter((session) => session.category === category.category).map((session) => <option key={session.upload_session_id} value={session.source_file_group_id}>{session.user_yyyymm} · {session.display_name} · {session.source_file_group_id.slice(0,8)}</option>)}
      </select>
    </Field>
  );
}
