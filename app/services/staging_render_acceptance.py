from html import escape

STAGING_RENDER_ACCEPTANCE_URL = "http://api:8000/staging/render-acceptance"
STAGING_ACCEPTANCE_SCENARIO = "missing_h1_resolution"

_resolved = False


def set_staging_render_acceptance_resolved(resolved: bool) -> None:
    global _resolved
    _resolved = resolved


def staging_render_acceptance_html(*, resolved: bool | None = None) -> str:
    page_resolved = _resolved if resolved is None else resolved
    heading = '<h1 id="acceptance-heading">Herstelde acceptatiepagina</h1>' if page_resolved else ""
    state = "resolved" if page_resolved else "missing-h1"
    return f"""<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Release 11 renderacceptatie</title>
  <meta name="description" content="Synthetische, klantvrije Release 11-testpagina.">
  <style>
    body {{ margin: 0; font: 18px/1.5 system-ui, sans-serif; background: #f3f7f4; color: #17352b; }}
    main {{
      max-width: 760px; margin: 96px auto; padding: 48px;
      background: white; border-radius: 18px;
    }}
    .badge {{
      display: inline-block; padding: 6px 10px;
      border-radius: 999px; background: #e7f4ec;
    }}
  </style>
</head>
<body data-acceptance-scenario="{escape(STAGING_ACCEPTANCE_SCENARIO)}"
      data-acceptance-state="{escape(state)}">
  <main>
    <span class="badge">Synthetische stagingtest</span>
    {heading}
    <p>Deze pagina bevat geen klantdata en is uitsluitend beschikbaar in staging.</p>
  </main>
</body>
</html>"""
