# SEMMA — Tu legado digital, protegido para siempre

Landing page oficial del proyecto Semma: bóveda cifrada de herencia digital.

## Cómo verla ahora

Abre `index.html` con doble clic en cualquier navegador. Ya funciona todo:
animaciones, contador de estadísticas, toggle EN/ES y formulario (en modo demo).

## Publicarla gratis en internet (GitHub Pages)

1. Crea una cuenta en github.com si no la tienes.
2. Crea un repositorio nuevo llamado `semma`.
3. Sube `index.html` (botón "Add file → Upload files").
4. En el repo: Settings → Pages → Source: `main` branch → Save.
5. En ~2 minutos tu web estará en `https://TU-USUARIO.github.io/semma/`

Cada actualización futura = editar el archivo en VS Code y hacer `git push`. Así de simple.

```bash
# flujo de trabajo diario desde VS Code en Linux
git add .
git commit -m "mejora en la sección de seguridad"
git push
```

## Activar la captura de emails REAL (gratis)

Ahora el formulario está en "modo demo". Para recibir emails de verdad:

1. Crea cuenta gratis en https://formspree.io (50 envíos/mes gratis).
2. Crea un formulario nuevo → te dan una URL tipo `https://formspree.io/f/abcd1234`.
3. En `index.html`, busca la línea:
   ```js
   const FORM_ENDPOINT = ''; // ← pega aquí tu endpoint de Formspree
   ```
   y pega tu URL entre las comillas.
4. Sube el cambio. Cada email de la lista de espera te llegará a tu correo.

## Estructura del proyecto (lo que viene)

```
semma/
├── index.html          ← landing page (FASE 1 ✅)
├── app/                ← la bóveda: registro, cifrado, activos (FASE 2)
└── backend/            ← Python FastAPI: usuarios, check-ins, protocolo (FASE 3)
```

## Roadmap

- [x] **Fase 1 — Landing + lista de espera.** Validar que hay interés. Compartir en
      r/CryptoCurrency, comunidades de expats en Londres, grupos de finanzas personales.
- [ ] **Fase 2 — La bóveda (frontend).** Registro de activos con cifrado en el navegador
      (Web Crypto API, AES-256). Nada sale sin cifrar.
- [ ] **Fase 3 — El interruptor (backend Python).** FastAPI + base de datos gratis
      (Supabase/Neon free tier) + emails de check-in + protocolo de escalada.
- [ ] **Fase 4 — Beneficiarios y entrega.** Flujo de desbloqueo para guardianes,
      periodos de espera anti-falsas-alarmas.
- [ ] **Fase 5 — Monetización.** Plan gratis (3 activos) vs. plan fundador (~£3/mes).

## Costes actuales: £0

- Hosting: GitHub Pages (gratis)
- Emails de lista de espera: Formspree (gratis hasta 50/mes)
- Backend futuro: Render/Railway free tier + Supabase free tier
- Único gasto recomendado cuando valides interés: dominio `semma.io` o `getsemma.com` (~£10/año)
