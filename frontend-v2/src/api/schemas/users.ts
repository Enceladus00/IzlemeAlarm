import { z } from 'zod';
import { apiDateTime, pageSchema } from './common';

/** user_service.py::_user_view */
export const userSchema = z.object({
  user_id: z.number(),
  username: z.string(),
  role_code: z.string(),
  is_active: z.boolean(),
  created_at: apiDateTime.nullable(),
});
export type User = z.infer<typeof userSchema>;
export const usersSchema = z.array(userSchema);

export const rolesSchema = z.array(z.object({ role_code: z.string(), name: z.string() }));
export type Role = z.infer<typeof rolesSchema>[number];

/** Limits from api_schemas.py and security.py (bcrypt accepts at most 72 bytes). */
export const USERNAME_MAX = 50;
export const PASSWORD_MAX_BYTES = 72;

/** audit_service.py::list_events */
export const auditEventSchema = z.object({
  audit_id: z.number(),
  actor_id: z.number().nullable(),
  action: z.string(),
  entity_type: z.string(),
  entity_id: z.string().nullable(),
  details: z.unknown().nullable(),
  created_at: apiDateTime,
});
export type AuditEvent = z.infer<typeof auditEventSchema>;
export const auditPageSchema = pageSchema(auditEventSchema);
