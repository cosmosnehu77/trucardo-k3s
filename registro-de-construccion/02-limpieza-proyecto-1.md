# #2 — Limpieza del Proyecto 1

| Campo | Valor |
| --- | --- |
| Issue | #2 |
| Rama | `issue-02-limpieza-proyecto-1` |
| Requisitos | RF-10, RNF-06 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Sacar del repositorio lo que era propio de la entrega del Proyecto 1 y presentar el repo como lo que es ahora: el proyecto de promoción.

## Qué se hizo
- **`Primer proyecto.docx`:** eliminado. Era el informe del Proyecto 1 (352 KB).
- **`.dockerignore`:** se quitó la regla `*.docx`. Sin documentos de Word en el repo, quedaba como configuración muerta.
- **`README.md`:** reescrito para la promoción:
  - qué es el proyecto y quiénes lo hacen;
  - el estado real hoy (en construcción);
  - los documentos de trabajo;
  - cómo correr lo que existe hoy con `docker compose`;
  - un resumen de las reglas de trabajo.
- **`PLAN.md`:** la tabla de estado marca la #2 como terminada.

## Por qué así
- **El README viejo no se copia (DRY).** La guía completa del Proyecto 1 sigue disponible en el tag `proyecto1-base`, y el README nuevo la enlaza. Copiar sus 500 líneas duplicaría un texto que ya no se va a mantener.
- **El README nuevo no promete lo que no existe (YAGNI).** No describe el despliegue en k3s porque todavía no está hecho; cada issue lo completa cuando lo construye (#8, #9 y #17).
- **Se conservan `demo.py`, `.env.ejemplo` y las instrucciones de `docker compose`.** Siguen siendo útiles: RF-10 pide que `docker compose` siga funcionando en una sola máquina. Sólo se quitó lo que pertenece a la **entrega** del Proyecto 1, no al software.
- **No se tocó `.gitignore`.** Sus reglas (`proj/`, `REFACTOR.md`, `ruff.toml`) son de uso local de quienes desarrollan y no publican nada.
- **Alternativa descartada:** mover el README viejo a un `docs/proyecto1.md`. Sería otra copia, igual que antes.

## Tests
No aplica: la issue no cambia código Python.

## Verificación
```
$ git ls-files | grep -ci docx
0
$ docker compose run --build --rm tests
168 tests, todo ok
$ docker compose run --rm tests
168 tests, todo ok
```

## Pendientes o riesgos detectados
- Ninguno nuevo. La siguiente es la **#3** (verificación automática de la suite). Ojo con la **#18** si el test de membresía vuelve a fallar.
