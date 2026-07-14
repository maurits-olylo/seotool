# Architectuurbesluiten

Dit document bewaart blijvende technische en productkeuzes. Nieuwe besluiten worden onderaan
toegevoegd met datum, context, keuze en gevolgen. Details van de implementatie staan in
`docs/architecture.md`.

## 2026-07-14 — Bestaande functionaliteit blijft leidend

Context: de repository bevat inmiddels gebruikers, klanttoegang, GSC, GA4, Bing, rapportages en
consultantinzichten, terwijl `AGENTS.md` enkele onderdelen oorspronkelijk als later werk benoemt.

Besluit: bestaande geteste functionaliteit wordt niet verwijderd of vereenvoudigd om het oude
MVP-kader opnieuw af te dwingen. `docs/roadmap.md` bepaalt de actuele uitvoeringsvolgorde.

Gevolg: nieuwe wijzigingen moeten compatibel blijven met de huidige productiefunctionaliteit.

## 2026-07-14 — Blijvende URL-identiteit en historische snapshots

Context: wijzigingen en issuehistorie vereisen een stabiele URL-identiteit over crawls heen.

Besluit: `urls` bewaart de blijvende identiteit, `url_snapshots` de toestand per meetmoment,
`changes` de verschillen en `issues` de actiepunten. Historische snapshots worden niet verwijderd
wanneer een URL verdwijnt.

Gevolg: actuele overzichten filteren op actieve URL's; historie en exports kunnen inactieve records
bewust blijven tonen.

## 2026-07-14 — Strikte website-scope zonder klantuitzonderingen

Context: gedeelde sitemaps en CMS-links koppelden `jobsatpearle.be` aan een andere website.

Besluit: alleen de basis-host, de equivalente www/root-variant en expliciet ingestelde subdomeinen
zijn intern. Scopecontrole geldt voor discovery, interne links, handmatige registratie en iedere
crawl. Bestaande externe records worden gedeactiveerd.

Gevolg: domeinisolatie is generiek en `jobsatpearle.be` kan later zelfstandig worden toegevoegd.

## 2026-07-14 — Atomaire klantonboarding

Context: losse klant- en websiteaanmaak kan half afgemaakte klantrecords achterlaten.

Besluit: de eerste klant en website worden in één transactie aangemaakt. Onboarding valideert en
normaliseert namen en referenties en maakt standaard website-instellingen aan.

Gevolg: een fout rolt de volledige onboarding terug; vervolgstappen mogen pas na commit worden
ingepland.

## 2026-07-14 — API-autorisatie is de beveiligingsgrens

Context: de interface verbergt functies per rol, maar UI-beperkingen zijn geen beveiliging.

Besluit: iedere beschermde route gebruikt een `Principal` en dwingt globale rol, klant- of
websitetoegang aan. De API-key blijft voor technische toegang; gebruikers werken met een beveiligde
sessiecookie en klantmemberships.

Gevolg: nieuwe UI-functionaliteit moet altijd een gelijkwaardige server-side autorisatiecontrole
hebben.

## 2026-07-14 — RQ voor werk en aparte exportqueue

Context: crawls, integraties en exports mogen HTTP-verzoeken niet blokkeren.

Besluit: persistente jobs worden via Redis/RQ uitgevoerd. Crawls gebruiken de standaardqueue en
exports een aparte `exports`-queue. De scheduler maakt alleen jobs aan; workers voeren ze uit.

Gevolg: API-, worker-, export-worker- en schedulerwijzigingen worden afzonderlijk beoordeeld bij
deployment.

## 2026-07-14 — Synology-releases via controleerbaar archive

Context: directe `scp` naar NAS-paden is onbetrouwbaar gebleken.

Besluit: releases worden lokaal met `git archive` gemaakt, met SHA-256 gecontroleerd en via
`ssh ... dd of=/tmp/...` geüpload. Op de NAS wordt pas na checksumcontrole uitgepakt.

Gevolg: ieder deploymentadvies vermeldt volledig pakketpad, checksum, migrationstatus en alleen de
geraakte containers.

## 2026-07-14 — Onpage- en noindex-issues vereisen indexatiecontext

Context: bewust niet-indexeerbare login-, filter- en hulppagina's veroorzaakten onnodige meldingen
over ontbrekende metadata, koppen en noindex-instructies.

Besluit: onpage-controles voor title, meta description en H1 gelden alleen voor indexeerbare
200-pagina's. Een noindex wordt alleen als onverwacht issue gemeld wanneer de URL in de actuele
sitemap staat of aantoonbare recente organische waarde heeft.

Gevolg: de actielijst bevat minder ruis, terwijl belangrijke pagina's met een onbedoelde noindex
met hoge urgentie gemeld blijven worden.

## 2026-07-14 — Semantische vergelijking voor wijzigingsdetectie

Context: CMS'en kunnen witruimte in koppen en de volgorde van JSON-LD `@graph`-onderdelen wijzigen
zonder dat de inhoud of betekenis verandert.

Besluit: H1-waarden worden voor vergelijking op witruimte genormaliseerd. JSON-LD-scriptblokken,
`@graph`-onderdelen en meervoudige `@type`-waarden worden als ongeordend vergeleken. De volgorde van
betekenisvolle lijsten, zoals `itemListElement`, blijft wel relevant.

Gevolg: technische herschikking veroorzaakt geen wijzigingsmelding, maar inhoudelijke structured
data-veranderingen blijven aantoonbaar zichtbaar.

## 2026-07-14 — Verouderde content alleen signaleren met expliciete datum

Context: ouderdom afleiden uit losse jaartallen of tekst levert te veel fout-positieve meldingen op.

Besluit: algemene contentouderdom wordt alleen als controlesignaal aangemaakt voor indexeerbare
redactionele schema's (`Article`, `BlogPosting`, `NewsArticle` en `TechArticle`) met een expliciete
`dateModified` of `datePublished` van minimaal drie jaar oud. Het signaal krijgt lage urgentie en
lage zekerheid; vacatures behouden hun eigen strengere verloopcontrole.

Gevolg: consultants krijgen een onderbouwde aanleiding voor inhoudelijke beoordeling zonder dat
ouderdom automatisch als SEO-fout wordt gepresenteerd.
