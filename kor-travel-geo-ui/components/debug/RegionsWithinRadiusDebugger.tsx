"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import type { z } from "zod";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { postJson } from "@/lib/api";
import { regionsWithinRadiusFormSchema } from "@/lib/schemas";
import {
  type RegionWithinRadiusLevel,
  useRegionsWithinRadiusStore
} from "@/lib/stores/regions-within-radius-store";
import type { components } from "@/types/api.gen";

type RegionsWithinRadiusInput = components["schemas"]["RegionsWithinRadiusInput"];
type RegionsWithinRadiusResponse = components["schemas"]["RegionsWithinRadiusResponse"];
type RegionsWithinRadiusFormInput = z.input<typeof regionsWithinRadiusFormSchema>;
type RegionsWithinRadiusFormValues = z.output<typeof regionsWithinRadiusFormSchema>;

const LEVEL_OPTIONS: { value: RegionWithinRadiusLevel; label: string }[] = [
  { value: "sido", label: "sido" },
  { value: "sigungu", label: "sigungu" },
  { value: "emd", label: "emd" }
];

export function RegionsWithinRadiusDebugger() {
  const draft = useRegionsWithinRadiusStore((state) => state.draft);
  const result = useRegionsWithinRadiusStore((state) => state.result);
  const setDraft = useRegionsWithinRadiusStore((state) => state.setDraft);
  const setResult = useRegionsWithinRadiusStore((state) => state.setResult);
  const queryClient = useQueryClient();
  const form = useForm<
    RegionsWithinRadiusFormInput,
    unknown,
    RegionsWithinRadiusFormValues
  >({
    defaultValues: draft,
    resolver: zodResolver(regionsWithinRadiusFormSchema)
  });
  const errors = form.formState.errors;
  const mutation = useMutation<
    RegionsWithinRadiusResponse,
    Error,
    RegionsWithinRadiusFormValues
  >({
    mutationFn: (values) => {
      const body: RegionsWithinRadiusInput = values;
      return postJson<RegionsWithinRadiusResponse>("/v2/regions/within-radius", body);
    },
    onMutate: (values) => {
      setDraft(values);
      setResult({ status: "LOADING" });
    },
    onSuccess: (response) => {
      setResult(response);
      void queryClient.invalidateQueries({ queryKey: ["regions-within-radius"] });
    },
    onError: (error) => {
      setResult({ error: error.message });
    }
  });

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>반경 행정구역</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form
          className="flex flex-col gap-4"
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
        >
          <FieldGroup className="grid gap-3 md:grid-cols-2">
            <Field data-invalid={Boolean(errors.lon)}>
              <FieldLabel htmlFor="region-lon">lon</FieldLabel>
              <Input
                aria-invalid={Boolean(errors.lon)}
                id="region-lon"
                inputMode="decimal"
                step="0.000001"
                type="number"
                {...form.register("lon", { valueAsNumber: true })}
              />
              <FieldError>{errors.lon?.message}</FieldError>
            </Field>
            <Field data-invalid={Boolean(errors.lat)}>
              <FieldLabel htmlFor="region-lat">lat</FieldLabel>
              <Input
                aria-invalid={Boolean(errors.lat)}
                id="region-lat"
                inputMode="decimal"
                step="0.000001"
                type="number"
                {...form.register("lat", { valueAsNumber: true })}
              />
              <FieldError>{errors.lat?.message}</FieldError>
            </Field>
          </FieldGroup>
          <Field data-invalid={Boolean(errors.radius_km)}>
            <FieldLabel htmlFor="region-radius-km">radius_km</FieldLabel>
            <Input
              aria-invalid={Boolean(errors.radius_km)}
              id="region-radius-km"
              inputMode="decimal"
              min="0"
              step="0.1"
              type="number"
              {...form.register("radius_km", { valueAsNumber: true })}
            />
            <FieldError>{errors.radius_km?.message}</FieldError>
          </Field>
          <Controller
            control={form.control}
            name="levels"
            render={({ field }) => (
              <FieldSet data-invalid={Boolean(errors.levels)}>
                <FieldLegend variant="label">levels</FieldLegend>
                <FieldGroup data-slot="checkbox-group" className="flex flex-row flex-wrap gap-3">
                  {LEVEL_OPTIONS.map((level) => {
                    const checked = field.value.includes(level.value);
                    return (
                      <Field key={level.value} orientation="horizontal">
                        <Checkbox
                          aria-invalid={Boolean(errors.levels)}
                          checked={checked}
                          id={`region-level-${level.value}`}
                          onCheckedChange={(nextChecked) => {
                            const nextLevels = nextChecked
                              ? Array.from(new Set([...field.value, level.value]))
                              : field.value.filter((value) => value !== level.value);
                            field.onChange(nextLevels);
                          }}
                        />
                        <FieldContent>
                          <FieldLabel htmlFor={`region-level-${level.value}`}>
                            {level.label}
                          </FieldLabel>
                        </FieldContent>
                      </Field>
                    );
                  })}
                </FieldGroup>
                <FieldError>{errors.levels?.message}</FieldError>
              </FieldSet>
            )}
          />
          <Button disabled={mutation.isPending} type="submit">
            <Radar data-icon="inline-start" />
            반경 조회
          </Button>
        </form>
        <JsonBlock value={result ?? { status: "READY" }} />
      </CardContent>
    </Card>
  );
}
