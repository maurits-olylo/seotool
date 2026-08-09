from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require(source: str, values: tuple[str, ...], label: str) -> None:
    missing = [value for value in values if value not in source]
    if missing:
        raise RuntimeError(f"{label} incomplete: {missing}")


def main() -> None:
    page = (PROJECT_ROOT / "app/ui/index.html").read_text()
    script = (PROJECT_ROOT / "app/ui/app.js").read_text()
    _require(
        page,
        (
            'id="insights-nav" class="nav-item">Inzichten</button>',
            'id="opportunities-nav" class="nav-item">Kansen</button>',
            'id="tasks-nav" class="nav-item">Acties',
            'aria-expanded="false">Metingen',
            'id="actions-nav">Signalen</button>',
            'id="content-effect-learning"',
        ),
        "Product navigation",
    )
    _require(
        script,
        (
            'insights: "inzichten"',
            'opportunities: "kansen"',
            'tasks: "acties"',
            '"analyse/acties": "actions"',
            '"analyse/content": "contentAnalysis"',
            'Dit is beschrijvende historie; causaliteit is niet bewezen.',
            'comparable.length < 3',
        ),
        "Route compatibility and learning safeguards",
    )
    print(
        {
            "status": "release_12_phase_f_staging_ok",
            "primary_navigation": ["Inzichten", "Kansen", "Acties"],
            "legacy_routes": True,
            "learning_minimum": 3,
            "causal_claim": False,
        }
    )


if __name__ == "__main__":
    main()
