# Acceptatieplan voor de resterende roadmap

Dit document bundelt de handmatige stagingacceptatie die naast geautomatiseerde tests nodig blijft.
Alle scenario's gebruiken synthetische websites, gebruikers en integratiegegevens. Productiedata en
echte externe accounts zijn geen acceptatiefixture.

## Vaste acceptatiegate per release

Iedere substantiële release doorloopt minimaal:

1. **Hoofdworkflow:** aanmaken of importeren, verwerken, zichtbaar resultaat, taakafhandeling en
   hercontrole vanuit de interface.
2. **Isolatie en rechten:** tweede tenant kan object, bestand, job en directe API-URL niet lezen of
   wijzigen; beheerder en gewone gebruiker zien alleen toegestane acties.
3. **Fout- en herstelpad:** time-out, ongeldige bron, dubbele start, workerherstart en retry leveren
   begrijpelijke statussen zonder dubbel resultaat of verloren historie.
4. **Interface:** desktop en 390 px mobiel, toetsenbordbediening, lokale laadstatus, lege toestand,
   foutmelding en refresh tijdens lopend werk.
5. **Operationeel:** migrations, minimale databaserollen, queue-admission, dead letters, auditlog,
   healthchecks, back-upimpact en rollbackgrens.

## Capabilityscenario's

| Onderdeel | Verplichte stagingproef | Doorslaggevend bewijs |
|---|---|---|
| Rendering en visuele inspectie | Ontbrekende H1 historisch vastleggen, pagina herstellen en live hercontroleren | Historische screenshot blijft staan; live status wordt `aanwezig`; geen automatische issueverificatie |
| Crawling en technische signalen | Kleine synthetische site met 200, redirect, 404, noindex, canonicalconflict, robotsblokkade en sitemapafwijking | Juiste gegroepeerde issues, bronbewijs en ruisarme lifecycle na tweede crawl |
| Takenworkflow | Taak oppakken, uitvoeren, automatische gerichte controle en zowel opgelost als niet-opgelost pad | Opgelost start effectmeting; niet opgelost heropent dezelfde taak zonder duplicaat |
| Analytics en Matomo/GA4 | Synthetische periodes met gekoppelde, ongekoppelde en ontbrekende URL's | Bron blijft herkenbaar; definities worden niet gemengd; koppelingsgraad klopt |
| Content- en vraagdekking | Informatieve site en webshopcatalogus met overlap, ontbrekend antwoord en onvoldoende bewijs | Advies schaalt per cluster; twijfel blijft review; geen harde actie zonder bewijs |
| Opportunity-engine | Potentieel met en zonder aantoonbare frictie, plus lage datadekking | Prioriteit is uitlegbaar en geen optelsom of algemene SEO-score |
| Externe intelligence | Fake provider met succes, leeg resultaat, quota, prijswijziging, time-out en replay | Kosten- en bronadministratie klopt; gebruiker ziet bruikbaar bewijs zonder providernaam |
| SERP, AI-citaties en concurrentie | Vragencluster met eigen vermelding, concurrentvermelding, ontbrekende citation en verouderde meting | Vraag-paginakoppeling en advies zijn reproduceerbaar; actualiteit en confidence zichtbaar |
| Effectmeting | Interventie met verbetering, verslechtering, onvoldoende meetduur en gelijktijdige wijziging | Correlatie wordt niet als causaliteit gepresenteerd; baseline en meetvenster blijven bewaard |
| Rapportage en export | Klant-, management- en detailweergave met lege en gedeeltelijke data | Cijfers sluiten aan op bronperiode; CSV/Excel respecteren tenant en filters |
| Onboarding en publieke ervaring | Uitnodiging, websiteverificatie, veilige defaults, mislukte verificatie en hervatting | Geen accountovername; geen crawl vóór verificatie; instructies en auditbewijs kloppen |
| Privacygate | Retentie, export, verwijdering, voorkeuren, afmelding en geïsoleerde restoreproef | Verwijdering werkt over alle opslaglagen; keuzes zijn versieerbaar; geen hoge bevindingen |
| Securitygate | IDOR/tenantisolatie, SSRF inclusief redirect en DNS-rebinding, sessie-intrekking, MFA en least privilege | Negatieve tests blokkeren aantoonbaar; auditlog bevat geen secrets; onafhankelijke restore slaagt |
| Begrensde AI | Budgetgrens, prijsbevestiging, promptinjectie, gevoelige invoer en providerfout | Geen stille kostenoverschrijding of datadoorgifte; deterministische fallback blijft bruikbaar |

## Herbruikbare stagingfixtures

De fixtures worden als een kleine catalogus opgebouwd, niet als losse productiecode per release.
Iedere fixture heeft een vaste scenario-ID, een begin- en eindtoestand, geen klantdata, een
idempotente seed en reset, en een machineleesbaar gereedsignaal. Interne uitzonderingen op
netwerkbeveiliging zijn alleen toegestaan voor exact geregistreerde staging-URL's; productie geeft
altijd `404` en houdt de gewone SSRF-regels.

De huidige eerste fixture heet `missing_h1_resolution`. Volgende fixtures worden pas toegevoegd
wanneer de bijbehorende roadmaprelease start, zodat de catalogus uitbreidbaar blijft zonder nu
ongebruikte productlogica te bouwen.
