# Overdracht SEO Tool

Bijgewerkt: 1 augustus 2026

## Startinstructie voor de nieuwe chat

Werk verder in `/Users/bibivanlijden/Documents/SEO Tool`. Lees vóór uitvoering volledig:

1. `AGENTS.md` en `CODEX-DEVELOPMENT-PROFILE.txt`;
2. `docs/HANDOFF-NEXT-CHAT.md` en `docs/roadmap.md`;
3. `DEVELOPMENT-INFRASTRUCTURE-CAPACITY.txt` alleen wanneer infrastructuur of taakverdeling
   relevant is.

Begin niet opnieuw bij de oorspronkelijke MVP. Controleer eerst Git en de actuele productie- of
stagingstatus die voor de eerstvolgende roadmaptaak nodig is. Laat de bestaande niet-gecommitte map
`outputs/` ongemoeid.

## Huidige versie en operationele toestand

- Laatste statuscommit vóór deze overdracht: `dc5bbdf`
  (`docs: record sitemap production validation`).
- Productiecode voor sitemapjobs: commit `31ad360` (`fix: process large sitemap indexes safely`).
- De latere commits `e1e4c41` en `dc5bbdf` wijzigen uitsluitend documentatie en voorkeuren en hoefden
  daarom niet opnieuw naar productie.
- Staging-API, productie-API en database waren na de laatste deployment gezond.
- Productieworkers `worker`, `crawl-worker-2` en `crawl-worker-3` draaien gezond met
  `MAX_SITEMAP_DOCUMENTS = 1000`.
- Migratiehead blijft `0035`; de sitemaprelease bevatte geen migration of datamutatie en vereiste
  daarom geen aanvullende databaseback-up.
- De volledige lokale testset voor de sitemapcorrectie slaagde: 333 tests; Ruff slaagde. De enige
  melding was een bestaande Starlette/httpx-deprecationwaarschuwing.

## Recent bereikt

### Automatische retentie

- Migratie `0035`, automatische retentie en hervatten via de scheduler zijn op staging en productie
  gevalideerd.
- Vijf productieoperaties eindigden als `succeeded`.
- In totaal zijn 185.741 oude, onbeschermde elementlocaties verwijderd in 19 batches.
- Onderhoud is afgerond; de normale crawltoestand was daarna hersteld.

### Betrouwbare sitemapjobs

- De oude crawler stopte stil na 100 sitemapdocumenten en meldde toch `succeeded`.
- HUMAN bleek één sitemapindex met 192 child-sitemaps te hebben. Daardoor werden voorheen slechts
  de index en 99 child-sitemaps verwerkt.
- De veiligheidslimiet is verhoogd naar 1.000 unieke documenten.
- Dubbele child-verwijzingen worden niet opnieuw ingepland.
- Als de limiet toch wordt bereikt, eindigt de job zichtbaar als `partially_succeeded` met het
  aantal nog niet verwerkte documenten. Ook een volledige sitecrawl kan dan niet onterecht volledig
  geslaagd heten.
- Productievalidatie HUMAN: `succeeded`, 193 sitemapdocumenten, 3.745 unieke URL's en circa 49
  seconden doorlooptijd. De oude afgeknotte import vond 2.789 URL's; de correctie maakte 956 extra
  URL's zichtbaar.

### Contextuele JobPosting-identifiers

- De actieve productie-worker bevat aantoonbaar de contextuele identifieranalyse.
- Schipper Kozijnen heeft 28 en GrandVision 507 actieve, indexeerbare vacatures zonder identifier;
  deze ontbreken blijven zonder inhoudelijk verwarringsrisico terecht stil.
- GrandVision leverde één echt overlapcluster van twee vacatures op met bron
  `cross_vacancy_similarity`, lage prioriteit en clusterbewijs.
- Het issue is na een latere geslaagde volledige crawl `verified`. Een aanvullende crawl of
  herberekening was niet nodig.

### Sitemapkwaliteit als later productonderdeel

- HUMAN en VPRO gebruiken vanuit hun gedeelde CMS een maandelijkse sitemapindeling.
- HUMAN had 192 child-sitemaps; VPRO had bij de controle 307 child-sitemaps.
- Dit aantal is technisch geldig en op zichzelf geen rankingfout, maar de bestanden zijn mogelijk
  onnodig sterk gefragmenteerd.
- Bij VPRO is concreet een `1970-01`-sitemap aangetroffen met vier URL's en een
  `1970-01-01T00:00:01.000Z`-waarde. Dit wijst op een epoch-fallback voor ontbrekende datummetadata.
- De roadmap bevat daarom later contextuele signalen voor overfragmentatie, lege of dubbele
  child-sitemaps, ontbrekende index-`lastmod` en ongeldige epoch-datums. Bouw deze niet buiten de
  geplande roadmapvolgorde.

### Publieke website-inschatting en F&F

- De veilige read-only backend voor publieke website-inschatting is lokaal technisch
  geïmplementeerd en getest; publieke UI, staging en productie volgen later.
- Pakketnamen, definitieve prijzen en twee of drie gratis maanden worden pas uitgewerkt wanneer de
  volledige roadmap klaar is voor de F&F-readinessbeoordeling.
- Onboarding is een verplichte roadmapfase vóór F&F, maar is nog niet gebouwd.
- F&F mag pas worden vrijgegeven nadat de volledige roadmapscope vanaf commit `71d732a` gereed,
  gedeployed en gevalideerd is, de gebruiker vindt dat het product ver genoeg is en de homepage in
  een afzonderlijke expliciete bevestiging klaar is verklaard.

## Eerstvolgende stap

Ga verder met de eerstvolgende open fase-4-taak in `docs/roadmap.md`: thin-contentdetectie verder
aanscherpen. Inspecteer eerst de bestaande implementatie, tests en productiebevindingen en bepaal
daarna een begrensde validatie- of correctiestap. Bouw de later geplande signalen voor algemene
verouderde content en sitemapkwaliteit niet buiten hun roadmapvolgorde.

## Vaste terminal- en deploymentvoorkeuren

- Communiceer in het Nederlands, maximaal vier uitvoeringsstappen en één fase tegelijk.
- Geef alleen volledig kopieerbare commandoblokken en noem het exacte bestaande terminalvenster,
  blokkering, normale duur, gereedsignaal en stopmoment.
- Voor een NAS-release: lokaal `git archive`, daarna uitsluitend streaming upload via
  `ssh thact@192.168.2.20 "dd of=/tmp/<release>.tar.gz" < /tmp/<release>.tar.gz` en alle verdere
  handelingen in de al geopende interactieve NAS-shell. Gebruik geen SCP en open geen tweede
  NAS-login.
- Gebruik geen hoekhaak-placeholder in een opdracht die letterlijk gekopieerd moet worden.
- De gebruiker controleert getoonde checksums zelf.
- Baseer `sleep` op gemeten doorlooptijd. Voor de HUMAN-sitemapjob is een eerste controle na 60
  seconden passend; controleer bij `pending` of `running` na 30 seconden opnieuw read-only.
- De pc/Linux-worker blijft een afzonderlijk infrastructuurproject en is nog niet beschikbaar voor
  de SEO Tool.

## Relevante recente commits

- `dc5bbdf` — documenteer sitemapproductievalidatie en gemeten wachttijden.
- `e1e4c41` — leg het vaste NAS-doel voor streaming SSH vast.
- `31ad360` — verwerk grote sitemapindexen veilig.
- `730a87d` — vereis expliciete homepagegoedkeuring vóór F&F.
- `a4c236b` — stel pakketuitwerking uit tot release-readiness.
- `bc5edf0` — voeg de publieke website-inschattingsbackend toe.
- `5780f9a` — blokkeer F&F tot de volledige bestaande roadmap gereed is.
- `71d732a` — plan onboarding als verplichte F&F-fase.
