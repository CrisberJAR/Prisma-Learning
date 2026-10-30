-- 006: ejercicios generados con IA por sesión (Fase 3) y respuestas evaluadas (Fase 4).
-- Pegar completo en Supabase -> SQL Editor -> Run. Es idempotente.

-- ---------------------------------------------------------------
-- Un conjunto de ejercicios por sesión. El docente lo genera, edita y publica.
-- items: [{id, tipo, enunciado, opciones[], correcta, explicacion}]
-- prompt: el texto exacto enviado a la IA (botón «Ver prompt»).
-- ---------------------------------------------------------------
create table if not exists conjuntos_ejercicios (
  id uuid primary key default gen_random_uuid(),
  sesion_id uuid not null unique references sesiones_material(id) on delete cascade,
  estado text not null default 'borrador' check (estado in ('borrador', 'publicado')),
  version int not null default 1,
  items jsonb not null default '[]',
  prompt text,
  modelo text,
  generado_por_ia boolean default true,
  editado_por_docente boolean default false,
  creado_en timestamptz default now(),
  actualizado_en timestamptz default now(),
  publicado_en timestamptz
);

-- ---------------------------------------------------------------
-- Un intento por estudiante y conjunto. items_snapshot congela las preguntas que vio,
-- así editar el conjunto después no altera evaluaciones ya hechas.
-- ---------------------------------------------------------------
create table if not exists respuestas_ejercicios (
  id uuid primary key default gen_random_uuid(),
  conjunto_id uuid not null references conjuntos_ejercicios(id) on delete cascade,
  sesion_id uuid not null references sesiones_material(id) on delete cascade,
  estudiante_id uuid not null references perfiles(id) on delete cascade,
  version int not null,
  items_snapshot jsonb not null,
  respuestas jsonb not null,
  resultado jsonb,
  informe jsonb,
  puntaje numeric(5, 2),
  estado text not null default 'enviado' check (estado in ('enviado', 'evaluado', 'error')),
  idioma text default 'es',
  creado_en timestamptz default now(),
  evaluado_en timestamptz,
  unique (conjunto_id, estudiante_id)
);

create index if not exists idx_respuestas_sesion on respuestas_ejercicios(sesion_id);
create index if not exists idx_respuestas_estudiante on respuestas_ejercicios(estudiante_id);

-- ---------------------------------------------------------------
-- RLS. El backend usa la clave de servicio; estas políticas cubren el acceso directo.
-- ---------------------------------------------------------------
alter table conjuntos_ejercicios enable row level security;
drop policy if exists conjuntos_docente on conjuntos_ejercicios;
create policy conjuntos_docente on conjuntos_ejercicios for all
  using (public.es_docente_de(public.curso_de_sesion(sesion_id)))
  with check (public.es_docente_de(public.curso_de_sesion(sesion_id)));
drop policy if exists conjuntos_estudiante_select on conjuntos_ejercicios;
create policy conjuntos_estudiante_select on conjuntos_ejercicios for select
  using (estado = 'publicado' and public.sesion_publicada(sesion_id) and public.esta_inscrito(public.curso_de_sesion(sesion_id)));

alter table respuestas_ejercicios enable row level security;
drop policy if exists respuestas_docente_select on respuestas_ejercicios;
create policy respuestas_docente_select on respuestas_ejercicios for select
  using (public.es_docente_de(public.curso_de_sesion(sesion_id)));
drop policy if exists respuestas_estudiante_select on respuestas_ejercicios;
create policy respuestas_estudiante_select on respuestas_ejercicios for select
  using (estudiante_id = auth.uid());
