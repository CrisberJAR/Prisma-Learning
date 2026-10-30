-- 005: idioma de la interfaz por usuario (es, en, pt, fr).
-- Pegar en Supabase -> SQL Editor -> Run. Es idempotente.
-- Sin esta columna la app funciona igual: el idioma solo se recuerda en la sesión del navegador.

alter table perfiles add column if not exists idioma_ui text;

alter table perfiles drop constraint if exists perfiles_idioma_ui_check;
alter table perfiles add constraint perfiles_idioma_ui_check
  check (idioma_ui is null or idioma_ui in ('es', 'en', 'pt', 'fr'));
