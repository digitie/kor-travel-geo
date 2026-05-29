import { z } from "zod";

export const addressTypeSchema = z.enum(["road", "parcel"]);
export const fallbackSchema = z.enum(["none", "api"]);

export const geocodeFormSchema = z.object({
  address: z.string().min(1).max(200),
  type: addressTypeSchema.default("road"),
  fallback: fallbackSchema.default("none")
});

export const reverseFormSchema = z.object({
  x: z.coerce.number().min(123).max(132),
  y: z.coerce.number().min(32).max(39),
  radius_m: z.coerce.number().int().min(1).max(2000).default(200)
});

export const normalizeFormSchema = z.object({
  address: z.string().min(1).max(200)
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
