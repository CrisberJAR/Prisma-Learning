-- 004: registro de estudiantes, contraseña temporal y borrado de sesiones.
-- Pegar completo en Supabase -> SQL Editor -> Run. Es idempotente (se puede volver a ejecutar).

-- ---------------------------------------------------------------
-- Perfiles: correo (para buscar cuentas sin recorrer auth.users)
-- y marca de "debe cambiar la contraseña temporal".
-- ---------------------------------------------------------------
alter table perfiles add column if not exists email text;
alter table perfiles add column if not exists debe_cambiar_clave boolean not null default false;

update perfiles p
set email = lower(u.email)
from auth.users u
where u.id = p.id and (p.email is null or p.email <> lower(u.email));

create unique index if not exists idx_perfiles_email on perfiles (lower(email));

-- El estudiante no puede quitarse la marca ni cambiar su rol desde su sesión;
-- solo el backend (clave de servicio) lo hace tras cambiar la contraseña.
drop policy if exists perfiles_update_self on perfiles;
create policy perfiles_update_self on perfiles for update using (id = auth.uid()) with check (
  id = auth.uid()
  and rol = (select rol from perfiles where id = auth.uid())
  and debe_cambiar_clave = (select debe_cambiar_clave from perfiles where id = auth.uid())
);

-- ---------------------------------------------------------------
-- Trigger: ahora también guarda el correo.
-- ---------------------------------------------------------------
create or replace function public.create_profile_if_not_exists()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_rol text := coalesce(new.raw_user_meta_data->>'rol', 'estudiante');
begin
  if v_rol not in ('docente', 'estudiante') then
    v_rol := 'estudiante';
  end if;
  insert into public.perfiles (id, nombre, rol, email)
  values (new.id, coalesce(new.raw_user_meta_data->>'nombre', new.email), v_rol, lower(new.email))
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users for each row execute function public.create_profile_if_not_exists();

-- ---------------------------------------------------------------
-- Borrar una sesión debe arrastrar su progreso (antes fallaba la FK).
-- ---------------------------------------------------------------
alter table interacciones_progreso drop constraint if exists interacciones_progreso_sesion_id_fkey;
alter table interacciones_progreso
  add constraint interacciones_progreso_sesion_id_fkey
  foreign key (sesion_id) references sesiones_material(id) on delete cascade;

-- Al desinscribir o borrar un curso, el estudiante no debe perder la cuenta,
-- pero sí sus inscripciones (ya en cascada por curso_id).
create index if not exists idx_inscripciones_curso on inscripciones_curso(curso_id);
