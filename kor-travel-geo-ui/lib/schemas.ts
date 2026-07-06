import { z } from "zod";

const addressTypeSchema = z.enum(["road", "parcel"]);
const fallbackSchema = z.enum(["none", "api"]);
const regionWithinRadiusLevelSchema = z.enum(["sido", "sigungu", "emd"]);

// 대한민국 좌표 범위 (EPSG:4326) — reverse/regionsWithinRadius가 공유한다.
const koreaLonSchema = z.coerce
  .number({ message: "경도는 숫자여야 합니다" })
  .min(123, "경도는 123~132 범위여야 합니다")
  .max(132, "경도는 123~132 범위여야 합니다");

const koreaLatSchema = z.coerce
  .number({ message: "위도는 숫자여야 합니다" })
  .min(32, "위도는 32~39 범위여야 합니다")
  .max(39, "위도는 32~39 범위여야 합니다");

export const geocodeFormSchema = z.object({
  address: z
    .string()
    .min(1, "주소를 입력하세요")
    .max(200, "주소는 200자 이하여야 합니다"),
  type: addressTypeSchema.default("road"),
  fallback: fallbackSchema.default("none")
});

export const reverseFormSchema = z.object({
  x: koreaLonSchema,
  y: koreaLatSchema,
  radius_m: z.coerce
    .number({ message: "반경은 숫자여야 합니다" })
    .int("반경은 정수여야 합니다")
    .min(1, "반경은 1~2000m 범위여야 합니다")
    .max(2000, "반경은 1~2000m 범위여야 합니다")
    .default(200)
});

export const regionsWithinRadiusFormSchema = z.object({
  lon: koreaLonSchema,
  lat: koreaLatSchema,
  radius_km: z.coerce
    .number({ message: "반경은 숫자여야 합니다" })
    .positive("반경은 0보다 커야 합니다")
    .max(500, "반경은 500km 이하여야 합니다")
    .default(3),
  levels: z.array(regionWithinRadiusLevelSchema).min(1, "레벨을 1개 이상 선택하세요")
});

export const normalizeFormSchema = z.object({
  address: z
    .string()
    .min(1, "주소를 입력하세요")
    .max(200, "주소는 200자 이하여야 합니다")
});

export const explainFormSchema = z.object({
  sql: z
    .string()
    .min(1)
    .refine((value) => /^(select|with)\b/i.test(value.trim()), {
      message: "SELECT 또는 WITH 쿼리만 허용"
    })
    .refine((value) => !value.includes(";"), {
      message: "세미콜론은 허용하지 않음"
    }),
  analyze: z.boolean().default(false),
  buffers: z.boolean().default(false)
});

// ---------------------------------------------------------------------------
// Admin 폼 공용 스키마 — 데이터 형태별 검증을 한 곳에서 정의한다.
// ---------------------------------------------------------------------------

/** PostgreSQL 식별자 (DB 이름 등): 소문자/숫자/밑줄, 문자로 시작, 63자 이하. */
export const pgIdentifierSchema = z
  .string()
  .regex(
    /^[a-z_][a-z0-9_]{0,62}$/,
    "소문자/숫자/밑줄만 사용하고 문자로 시작해야 합니다 (63자 이하)"
  );

/** http(s) URL — callback URL, RustFS endpoint 등. (zod v4 top-level format) */
export const httpUrlSchema = z
  .url({ message: "http:// 또는 https:// URL 형식이어야 합니다" })
  .refine((value) => /^https?:\/\//.test(value), {
    message: "http:// 또는 https:// URL 형식이어야 합니다"
  });

/** S3 버킷 이름 규칙 (소문자/숫자/하이픈, 3-63자). */
export const s3BucketSchema = z
  .string()
  .regex(
    /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/,
    "버킷 이름은 소문자/숫자/하이픈 3~63자여야 합니다"
  );
