# Roadmapdekking en aanvullingen — 2 augustus 2026

## Doel

Dit document vergelijkt de aangeleverde 45 roadmaponderdelen met de bestaande projectroadmap.
De bestaande code en productievalidaties blijven leidend: gerealiseerde functionaliteit wordt niet
opnieuw gebouwd. `docs/roadmap.md` blijft de actuele uitvoeringsplanning.

## Dekking

### Matrix van de 45 aangeleverde onderdelen

| Nr. | Onderdeel | Dekking in bestaande roadmap | Verwerking |
|---:|---|---|---|
| 1 | Databaseopschoning en retentie | Gedeeltelijk | Uitgebreid per datatype in Release A |
| 2 | Productievalidatie meerdere klanten | Aanwezig, in uitvoering | Behouden in Release A |
| 3 | Crawlcapaciteit en wachtrijen | Grotendeels aanwezig | Uitgebreid met prioriteit, backpressure en dead-letter-afhandeling |
| 4 | Sitemapjobs | Aanwezig en grotendeels gevalideerd | Regressies blijven in Release A |
| 5 | Productieafronding en runbook | Gedeeltelijk | Compleet runbook toegevoegd aan Release A |
| 6 | Google URL Inspection | Gepland | Behouden in Release B |
| 7 | Hreflang | Gepland | Behouden in Release B |
| 8 | Soft 404 | Gepland | Behouden in Release B |
| 9 | Canonical-integriteit | Gepland | Behouden en gekoppeld aan URL Inspection/hreflang |
| 10 | Beperkte JavaScript-rendering | Gepland | Behouden met aparte renderqueue |
| 11 | Asset- en medialokalisatie | Alleen gedeeltelijk bewijs aanwezig | Blijvend register toegevoegd |
| 12 | Live elementlokalisatie | Eerste versie aanwezig | Uitbreiding en productievalidatie behouden |
| 13 | Diagnoses vereenvoudigen | Aanwezig, in uitvoering | Gebundeld in Release C |
| 14 | Aanbevelingen vereenvoudigen | Aanwezig, in uitvoering | Gebundeld in Release C |
| 15 | Uitvoeringstaken | Aanwezig, deels gedeployed | Afronding in Release C |
| 16 | URL-overzicht | Technische basis aanwezig | Uitgebreid met bron- en meetdekking |
| 17 | Gerichte exports | Basis gedeployed | Uitgebreid met kolommen en nieuwe datatypen |
| 18 | Crawldiepte uitleggen | Technisch aanwezig | Productievalidatie in Release A/C |
| 19 | Matomo | Gepland | Behouden in Release D |
| 20 | Zoekintentie | Gepland | Behouden en uitgebreid met lokale/recruitmentcontext |
| 21 | Contentkwaliteit | Alleen deels via thin content/opportunities | Nieuwe bewijsgebonden module |
| 22 | Contentveroudering | Gepland | Uitgebreid met bronnen, downloads en risicoprioriteit |
| 23 | Kannibalisatie/contentoverlap | Deels in opportunitypatronen | Zelfstandige analyse toegevoegd |
| 24 | Interne-linkkansen | Alleen semantische basis gepland | Nieuwe opportunitymodule |
| 25 | Opportunity-engine | Uitgebreid gepland | Behouden in Release D |
| 26 | Genormaliseerde externe links | Bing-bron bestaat, generiek model ontbreekt | Nieuwe module in Release E |
| 27 | DataForSEO | Niet aanwezig | Nieuwe begrensde provideroptie |
| 28 | Ahrefs/Majestic | Niet aanwezig | Latere provider achter dezelfde interface |
| 29 | Linkwaardeclassificatie | Niet aanwezig | Nieuwe verklaarbare kenmerken, geen linkscore |
| 30 | Leveranciers-/partnerkansen | Niet aanwezig | Nieuwe opportunitypatronen |
| 31 | Concurrentieanalyse | Alleen als latere externe bron genoemd | Nieuwe afgebakende module |
| 32 | SERP-/zichtbaarheidstracking | Alleen leveranciersstrategie aanwezig | Nieuwe budgetgestuurde module |
| 33 | Geautomatiseerde prioritering | Uitgebreid gepland | Bestaande opportunityweging blijft leidend |
| 34 | Impactmeting | Gepland | Behouden en uitgebreid met indexatie/rankings |
| 35 | Management-/klantrapportages | Gedeeltelijke rapportbasis aanwezig | Uitgebreid; PDF pas na stabiele inhoud |
| 36 | AI-gebruiksmodel | Niet aanwezig | Nieuwe commerciële en technische basis |
| 37 | Prijsindicatie vooraf | Niet aanwezig | Nieuwe verplichte bevestigingsgate |
| 38 | AI-budgetten | Niet aanwezig | Nieuwe harde limieten en waarschuwingen |
| 39 | AI-gebruikslogboek | Niet aanwezig | Nieuwe audit- en exportmodule |
| 40 | Beperkte AI-functies | Richting aanwezig | Concrete eerste functies vastgelegd |
| 41 | Bulkbeperkingen | Niet aanwezig | Nieuwe begrenzing |
| 42 | AI-kwaliteit/veiligheid | Richting aanwezig | Uitgebreid tot acceptatie-eisen |
| 43 | AI-impactbijdrage | Niet aanwezig | Transparantiekader toegevoegd, geen CO₂-claim |
| 44 | AI-providerabstractie | Richting aanwezig | Verplicht fundament vóór generatie |
| 45 | AI-tests | Niet aanwezig als volledige set | Verplichte testmatrix voor Release G |

### Reeds aanwezig of al substantieel gespecificeerd

- Multi-clientvalidatie, tenantisolatie, crawl-admission en gescheiden crawlqueues.
- Betrouwbare sitemapjobs, blijvend URL-register en historische URL-status.
- Google URL Inspection, hreflang, soft 404, canonical-integriteit en begrensde JavaScriptcontrole.
- Live elementlokalisatie en elementbewijs.
- Diagnoseclustering, bewijsgebonden adviezen, uitvoeringstaken en gerichte verificatiecrawls.
- URL-overzicht, crawldiepte met kortste interne route en gerichte CSV-/Excel-exports.
- Matomo, zoekintentie, contentveroudering, opportunity-engine en verklaarbare prioritering.
- Impactmeting na uitvoering, periodevergelijkingen en voorzichtig omgaan met causaliteit.
- Optionele AI-advieslaag en provideronafhankelijkheid als richting.

### Aanwezig, maar door de nieuwe roadmap concreter of breder gemaakt

1. **Retentie:** naast elementlocaties expliciet beleid voor crawlresponses, wijzigingsdetails,
   ruwe integratie-imports en GSC-detaildata, met behoud van aggregaties en voor-/narapport.
2. **Queuebeheer:** prioriteit en limiet per website, backpressure, dead-letter-afhandeling en aparte
   sitemap- en renderqueues toevoegen aan de bestaande light-, full-, verificatie-, integratie- en
   exportqueues.
3. **Operationeel beheer:** één runbook voor deploy, rollback, restore, vastgelopen worker/crawl,
   defecte import, overvolle queue en schijfruimteprobleem.
4. **Asset- en medialokalisatie:** uitbreiden van bestaand element- en assetbewijs naar een blijvend
   register voor afbeeldingen, video, PDF, downloads en externe assets met gebruikende pagina's.
5. **URL-overzicht:** bronaanwezigheid uit sitemap, interne links, GSC, GA4, Matomo en Bing naast
   lifecycle, indexeerbaarheid, belangrijkste diagnose en meetwaarden tonen.
6. **Exports:** actieve selectie uitbreiden met kolomkeuze, sortering, taken, backlinks, analytics
   en verificatiestatus; grote exports blijven achtergrondjobs.
7. **Contentanalyse:** contentkwaliteit, kannibalisatie en interne-linkkansen als afzonderlijke,
   bewijsgebonden modules uitwerken zonder algemene contentscore.
8. **Rapportage:** klantvriendelijke samenvatting en technische bijlage met periodevergelijking;
   PDF wordt pas toegevoegd wanneer inhoud en visuele template stabiel zijn.

### Nieuwe modules

1. **Genormaliseerd extern-linkmodel**
   - Combineer Bing en toekomstige providers zonder bronmetrics stil samen te voegen.
   - Bewaar bron- en doeldomein, URL's, anker, eerste/laatste waarneming, status, followstatus,
     provider, relevantiebewijs en beschikbaar verwijzend verkeer.
   - Dedupliceer dezelfde waargenomen link provideroverschrijdend, maar behoud bronbewijs.
2. **Betaalde SEO-dataproviders**
   - Maak één providerinterface voor DataForSEO en later eventueel Ahrefs of Majestic.
   - Start met precies één provider en één aantoonbare use-case; activeer SERP, zoekvolume,
     concurrentie en backlinks niet automatisch als één onbeperkt pakket.
   - Bewaar kostenbudget, cache, quota, frequentie en kosten per job. Providerlogica komt niet in de
     UI of generieke domeinmodellen.
3. **Linkwaarde en relatiekansen**
   - Classificeer relevantie, context, followstatus, continuïteit, verwijzend verkeer en mogelijke
     leverancier-, partner- of publicatierelatie als afzonderlijke verklarende kenmerken.
   - Gebruik geen generieke linkscore en label een link niet automatisch slecht op basis van één
     externe domeinmetric.
4. **Concurrentie- en SERP-module**
   - Onderscheid zoek-, bedrijfs- en contentconcurrenten.
   - Volg positie, ranking-URL, SERP-feature, apparaat, locatie, intentie en verandering binnen
     expliciete budgetten en meetfrequenties.
5. **Volledig AI-gebruiks- en afrekenmodel**
   - Centraal model voor provider, model, input-/outputtokens, outputwoorden, werkelijke kosten,
     gebruikersbijdrage, tegoed, budget, status, retries en audit.
   - Ondersteun uitschakeling en harde limieten per klant en website, waarschuwingen en expliciete
     prijsbevestiging vóór iedere opdracht.
   - Tarief, minimum, inbegrepen tegoed en limieten zijn configureerbaar en versieerbaar; bedragen
     worden niet hardcoded en nog niet als definitieve commerciële prijs gepubliceerd.
   - Voorgestelde werkwaarden zijn €0,002 per outputwoord, minimaal €0,05 per opdracht en €1,00
     maandelijks tegoed per betaald abonnement. Definitieve invoering vereist toetsing aan
     providerkosten, btw, facturatie, mislukte opdrachten en de later vast te stellen pakketten.
   - Gebruik de transparante term `AI-gebruiksbijdrage`; claim geen exacte CO₂-compensatie.

## Behouden onderdelen die in de aangeleverde roadmap ontbraken

- Publieke website-inschatting en pakketadvies.
- Publieke vraagassistent met eerlijke vergelijking en doorverwijzing.
- Strikt gescheiden in-product contextuele data-assistent.
- Analytics-anomaliedetectie en meetvalidatie tijdens onboarding.
- Lighthouse/CrUX als bewijs voor uitvoerbare performanceacties.
- Invitation-only onboarding met eigendomsverificatie.
- Friends-and-family-readinessgates en de twee afzonderlijke deploymentbevestigingen.
- Pakketdefinitie, gratis gebruikstermijn en commerciële publicatie pas na roadmapafronding.

## Aanvullende acceptatieregels

- Een grote crawl blokkeert een gerichte verificatie of kleine sitemapcontrole niet.
- Een gerichte verificatie verschuift de volgende volledige crawl niet.
- Verwijderde detaildata laat verklaarbare aggregaties, lifecycle en auditgeschiedenis intact.
- Externe providerdata toont altijd bron, meetdatum, dekking, quota en kostencontext.
- AI start nooit zonder voldoende budget en expliciete bevestiging van de maximale bijdrage.
- Retry, afbreken of workerherstart veroorzaakt geen dubbele providerbetaling of facturatie.
- AI-output blijft concept, wordt niet automatisch gepubliceerd en gebruikt minimale klantdata.
- Nieuwe publieke en commerciële functionaliteit omzeilt de bestaande releasegates niet.
