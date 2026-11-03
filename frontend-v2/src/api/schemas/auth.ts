import { z } from 'zod';

/** POST /auth/login (backend/api/routes/auth.py). */
export const tokenResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.string(),
  expires_in: z.number().int().positive(),
});
export type TokenResponse = z.infer<typeof tokenResponseSchema>;

/** GET /auth/me. Note: the API does not return a user id. */
export const profileSchema = z.object({
  username: z.string(),
  role_code: z.string(),
  permissions: z.array(z.string()),
});
export type Profile = z.infer<typeof profileSchema>;
